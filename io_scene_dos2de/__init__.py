# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

if "bpy" in locals():
    import importlib
    if "export_dae" in locals():
        importlib.reload(export_dae) # noqa

from pathlib import Path
import tempfile
import bpy
import bmesh
import os
import os.path
import subprocess
import xml.etree.ElementTree as et

from bpy.types import Operator, AddonPreferences, PropertyGroup, UIList, Panel
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty, CollectionProperty, PointerProperty, IntProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper

from math import radians, degrees
from mathutils import Euler, Matrix

from . import export_dae

bl_info = {
    "name": "DOS2/BG3 Collada Exporter",
    "author": "LaughingLeader / Norbyte",
    "blender": (3, 6, 0),
    "version": (2, 0, 0),
    "location": "File > Import-Export",
    "description": ("Export Collada/Granny files for Divinity Original Sin / Baldur's Gate 3."),
    "warning": "",
    "doc_url": "",
    "tracker_url": "",
    "support": "COMMUNITY",
    "category": "Import-Export"
}

gr2_extra_flags = (
    ("DISABLED", "Disabled", ""),
    ("MESHPROXY", "MeshProxy", "Flags the mesh as a meshproxy, used for displaying overlay effects on a weapon and AllSpark MeshEmiters"),
    ("CLOTH", "Cloth", "The mesh has vertex painting for use with Divinity's cloth system"),
    ("RIGID", "Rigid", "For meshes lacking an armature modifier. Typically used for weapons"),
    ("RIGIDCLOTH", "Rigid&Cloth", "For meshes lacking an armature modifier that also contain cloth physics. Typically used for weapons")
)

game_versions = (
    ("dos", "DOS", "Divinity: Original Sin"),
    ("dosee", "DOS: EE", "Divinity: Original Sin - Enhanced Edition"),
    ("dos2", "DOS 2", "Divinity: Original Sin 2"),
    ("dos2de", "DOS 2: DE", "Divinity: Original Sin 2 - Definitive Edition"),
    ("bg3", "BG 3", "Baldur's Gate 3"),
    ("unset", "Unset", "Unset")
)

current_operator = None
IS_TRACING = True

def report(msg, reportType="WARNING"):
    if current_operator is not None:
        current_operator.report(set((reportType, )), msg)
    print("{} ({})".format(msg, reportType))

def trace(msg):
    if IS_TRACING:
        print(msg)

def get_prefs(context):
    return context.preferences.addons["io_scene_dos2de"].preferences

class ProjectData(PropertyGroup):
    project_folder: StringProperty(
        name="Project Folder",
        description="The root folder where .blend files are stored"
    )
    export_folder: StringProperty(
        name="Export Folder",
        description="The root export folder"
    )

class ProjectEntry(PropertyGroup):
    project_data: CollectionProperty(type=ProjectData)
    index: IntProperty()

class DIVINITYEXPORTER_OT_add_project(Operator):
    bl_idname = "divinityexporter.add_project"
    bl_label = "Add Project"
    bl_description = "Add an entry to the project list"

    def execute(self, context):
        get_prefs(context).projects.project_data.add()
        return {'FINISHED'}

class DIVINITYEXPORTER_OT_remove_project(Operator):
    bl_idname = "divinityexporter.remove_project"
    bl_label = "Remove"
    bl_description = "Remove Project"

    selected_project: CollectionProperty(type=ProjectData)

    def set_selected(self, item):
        selected_project = item

    def execute(self, context):
        addon_prefs = get_prefs(context)

        i = 0
        for project in addon_prefs.projects.project_data:
            if (project.project_folder == self.selected_project[0].project_folder
                and project.export_folder == self.selected_project[0].export_folder):
                    addon_prefs.projects.project_data.remove(i)
            i += 1

        self.selected_project.clear()

        return {'FINISHED'}

class DIVINITYEXPORTER_UL_project_list(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "project_folder", text="Project Folder")
            layout.prop(item, "export_folder", text="Export Folder")
            op = layout.operator("divinityexporter.remove_project", icon="CANCEL", text="", emboss=False)
            #Is there no better way?
            project = op.selected_project.add()
            project.project_folder = item.project_folder
            project.export_folder = item.export_folder

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class DIVINITYEXPORTER_AddonPreferences(AddonPreferences):
    bl_idname = "io_scene_dos2de"

    lslib_path: StringProperty(
        name="Divine Path",
        description="The path to divine.exe, used to convert from dae to gr2",
        subtype='FILE_PATH',
    )
    gr2_default_enabled: BoolProperty(
        name="Convert to GR2 by Default",
        default=True,
        description="Models will be converted to gr2 by default if the Divine Path is set"
    )

    default_preset: EnumProperty(
        name="Default Preset",
        description="The default preset to load when the exporter is opened for the first time",
        items=(("NONE", "None", ""),
               ("MESHPROXY", "MeshProxy", "Use default meshproxy settings"),
               ("ANIMATION", "Animation", "Use default animation settings"),
               ("MODEL", "Model", "Use default model settings")),
        default=("NONE")
    )

    auto_export_subfolder: BoolProperty(
        name="Use Preset Type for Project Export Subfolder",
        description="If enabled, the export subfolder will be determined by the preset type set.\nFor instance, Models go into \Models",
        default=False
    )

    projects: PointerProperty(
        type=ProjectEntry,
        name="Projects",
        description="Project pathways to auto-detect when exporting"
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Divinity Export Addon Preferences")
        layout.prop(self, "lslib_path")
        layout.prop(self, "gr2_default_enabled")
        layout.prop(self, "default_preset")
        layout.prop(self, "auto_export_subfolder")

        layout.separator()
        layout.label(text="Projects")
        layout.template_list("DIVINITYEXPORTER_UL_project_list", "", self.projects, "project_data", self.projects, "index")
        layout.operator("divinityexporter.add_project")

class GR2_ExportSettings(PropertyGroup):
    """GR2 Export Options"""

    extras: EnumProperty(
        name="Flag",
        description="Flag every mesh with the selected flag.\nNote: Custom Properties on a mesh will override this",
        items=gr2_extra_flags,
        default=("DISABLED")
    )
    yup_conversion: BoolProperty(
        name="Convert to Y-Up",
        default=True
    )
    force_legacy: BoolProperty(
        name="Force Legacy GR2 Version Tag",
        default=False
    )
    create_dummyskeleton: BoolProperty(
        name="Create Dummy Skeleton",
        default=True
    )

    def draw(self, context, obj):
        obj.label(text="GR2 Options")
        obj.prop(self, "yup_conversion")
        obj.prop(self, "force_legacy")
        obj.prop(self, "create_dummyskeleton")

        obj.label(text="Extra Properties (Global)")
        obj.prop(self, "extras")
        #extrasobj = obj.row(align=False)
        #self.extras.draw(context, extrasobj)

class Divine_ExportSettings(PropertyGroup):
    """Divine GR2 Conversion Settings"""
    gr2_settings: bpy.props.PointerProperty(
        type=GR2_ExportSettings,
        name="GR2 Export Options"
    )

    game: EnumProperty(
        name="Game",
        description="The target game. Currently determines the model format type",
        items=game_versions,
        default=("dos2de")
    )

    xflip_skeletons: BoolProperty(
        name="X-Flip Skeletons",
        default=False
    )

    flip_uvs: BoolProperty(
        name="Flip UVs",
        default=True
    )
    filter_uvs: BoolProperty(
        name="Filter UVs",
        default=False
    )
    ignore_uv_nan: BoolProperty(
        name="Ignore Bad NaN UVs",
        description="Ignore bad/unwrapped UVs that fail to form a triangle. Export will fail if these are detected",
        default=False
    )
    export_normals: BoolProperty(
        name="Export Normals",
        default=True
    )
    export_tangents: BoolProperty(
        name="Export Tangent/Bitangent",
        default=True
    )
    export_uvs: BoolProperty(
        name="Export UVs",
        default=True
    )
    export_colors: BoolProperty(
        name="Export Colors",
        default=True
    )
    deduplicate_vertices: BoolProperty(
        name="Deduplicate Vertices",
        default=True
    )
    deduplicate_uvs: BoolProperty(
        name="Deduplicate UVs",
        default=True
    )
    recalculate_normals: BoolProperty(
        name="Recalculate Normals",
        default=False
    )
    recalculate_tangents: BoolProperty(
        name="Recalculate Tangent/Bitangent",
        default=False
    )
    recalculate_iwt: BoolProperty(
        name="Recalculate Inverse World Transforms",
        default=False
    )
    disable_qtangents: BoolProperty(
        name="Disable QTangents",
        default=False
        )

    keep_bind_info: BoolProperty(
		name="Keep Bind Info",
		description="Store Bindpose information in custom bone properties for later use during Collada export",
		default=True)

    navigate_to_blendfolder: BoolProperty(default=False)

    drawable_props = [
        "xflip_skeletons",
        "flip_uvs",
        "filter_uvs",
        "ignore_uv_nan",
        "export_normals",
        "export_tangents",
        "export_uvs",
        "export_colors",
        "deduplicate_vertices",
        "deduplicate_uvs",
        "recalculate_normals",
        "recalculate_tangents",
        "recalculate_iwt",
        "disable_qtangents"
    ]


    def draw(self, context, obj):
        obj.prop(self, "game")
        obj.label(text="GR2 Export Settings")
        gr2box = obj.box()
        self.gr2_settings.draw(context, gr2box)

        #col = obj.column(align=True)
        obj.label(text="Export Options")
        for prop in self.drawable_props:
            obj.prop(self, prop)

class DivineInvoker:
    def __init__(self, addon_prefs, divine_prefs):
        self.addon_prefs = addon_prefs
        self.divine_prefs = divine_prefs

    def check_lslib(self):
        if self.addon_prefs.lslib_path is None or self.addon_prefs.lslib_path == "":
            report("LSLib path was not set up in addon preferences. Cannot convert to GR2.", "ERROR")
            return False
            
        lslib_path = Path(self.addon_prefs.lslib_path)
        if not lslib_path.is_file():
            report("The LSLib path set in addon preferences is invalid. Cannot convert to GR2.", "ERROR")
            return False
        
        return True

    def build_gr2_options(self):
        export_str = ""
        # Possible args:
        #"export-normals;export-tangents;export-uvs;export-colors;deduplicate-vertices;
        # deduplicate-uvs;recalculate-normals;recalculate-tangents;recalculate-iwt;flip-uvs;
        # force-legacy-version;compact-tris;build-dummy-skeleton;apply-basis-transforms;conform"

        divine_args = {
            "xflip_skeletons"           : "x-flip-skeletons",
            "export_normals"            : "export-normals",
            "export_tangents"           : "export-tangents",
            "export_uvs"                : "export-uvs",
            "export_colors"             : "export-colors",
            "deduplicate_vertices"      : "deduplicate-vertices",
            "deduplicate_uvs"           : "deduplicate-uvs",
            "recalculate_normals"       : "recalculate-normals",
            "recalculate_tangents"      : "recalculate-tangents",
            "recalculate_iwt"           : "recalculate-iwt",
            "flip_uvs"                  : "flip-uvs",
            "ignore_uv_nan"             : "ignore-uv-nan",
            "disable_qtangents"         : "disable-qtangents"
        }

        gr2_args = {
            "force_legacy"              : "force-legacy-version",
            "create_dummyskeleton"      : "build-dummy-skeleton",
            "yup_conversion"            : "apply-basis-transforms",
            #"conform"					: "conform"
        }

        for prop,arg in divine_args.items():
            val = getattr(self.divine_prefs, prop, False)
            if val == True:
                export_str += "-e " + arg + " "

        gr2_settings = self.divine_prefs.gr2_settings

        for prop,arg in gr2_args.items():
            val = getattr(gr2_settings, prop, False)
            if val == True:
                export_str += "-e " + arg + " "

        return export_str

    def dae_to_gr2(self, collada_path, gr2_path):
        if not self.check_lslib():
            return False
        gr2_options_str = self.build_gr2_options()
        divine_exe = '"{}"'.format(self.addon_prefs.lslib_path)
        game_ver = bpy.context.scene.ls_properties.game
        proccess_args = "{} --loglevel all -g {} -s {} -d {} -i dae -o gr2 -a convert-model {}".format(
            divine_exe, game_ver, '"{}"'.format(collada_path), '"{}"'.format(gr2_path), gr2_options_str
        )
        
        print("[DOS2DE-Collada] Starting GR2 conversion using divine.exe.")
        print("[DOS2DE-Collada] Sending command: {}".format(proccess_args))

        process = subprocess.run(proccess_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

        print(process.stdout)
        print(process.stderr)
        
        if process.returncode != 0:
            error_message = "Failed to convert Collada to GR2. {}".format(
                '\n'.join(process.stdout.splitlines()[-1:]) + '\n' + process.stderr)
            report(error_message, "ERROR")
            return False
        else:
            return True

    def gr2_to_dae(self, gr2_path, collada_path):
        if not self.check_lslib():
            return False
        divine_exe = '"{}"'.format(self.addon_prefs.lslib_path)
        proccess_args = "{} --loglevel all -g bg3 -s {} -d {} -i gr2 -o dae -a convert-model -e flip-uvs".format(
            divine_exe, '"{}"'.format(gr2_path), '"{}"'.format(collada_path)
        )
        
        print("[DOS2DE-Collada] Starting DAE conversion using divine.exe.")
        print("[DOS2DE-Collada] Sending command: {}".format(proccess_args))

        process = subprocess.run(proccess_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

        print(process.stdout)
        print(process.stderr)
        
        if process.returncode != 0:
            error_message = "Failed to convert GR2 to Collada. {}".format(
                '\n'.join(process.stdout.splitlines()[-1:]) + '\n' + process.stderr)
            report(error_message, "ERROR")
            return False
        else:
            return True


class ExportTargetCollection:
    __slots__ = ("targets", "ordered_targets")

    def __init__(self):
        self.targets = {}
        self.ordered_targets = []

    def should_export(self, obj):
        return obj.name in self.targets

    def is_root(self, obj):
        return self.should_export(obj) and (obj.parent is None or not self.should_export(obj.parent))

    def add(self, obj):
        self.targets[obj.name] = obj


class ExportTargetCollector:
    __slots__ = ("options")

    def __init__(self, options):
        self.options = options

    def collect(self, objects):
        collection = ExportTargetCollection()
        trace(f'Collecting objects to export:')
        self.collect_objects(objects, collection)
        if 'ARMATURE' in self.options.object_types:
            self.collect_parents(collection)
        self.build_target_order(collection)
        return collection


    # Need to make sure that we're going parent -> child order when applying transforms,
    # otherwise a modifier/transform apply step on the parent could leave the child transform unapplied
    def build_target_order(self, collection: ExportTargetCollection):
        for obj in collection.targets.values():
            if collection.is_root(obj):
                collection.ordered_targets.append(obj)
                self.build_target_children(collection, obj)


    def build_target_children(self, collection: ExportTargetCollection, obj):
        for child in obj.children:
            if collection.should_export(child):
                collection.ordered_targets.append(child)
                self.build_target_children(collection, child)


    def collect_objects(self, objects, collection: ExportTargetCollection):
        for obj in objects:
            if not collection.should_export(obj):
                if self.should_export_object(obj):
                    collection.add(obj)
                    #self.add_objects_recursive(obj.children, collection)


    def add_objects_recursive(self, objects, collection: ExportTargetCollection):
        for obj in objects:
            trace(f' - {obj.name}: Marked for export because a parent will export')
            collection.add(obj)
            self.add_objects_recursive(obj.children, collection)


    def collect_parents(self, collection: ExportTargetCollection):
        for obj in list(collection.targets.values()):
            if obj.parent is not None and not collection.should_export(obj.parent) and obj.parent.type == "ARMATURE":
                trace(f' - {obj.parent.name}: Marked for export because a child with armature modifier will export')
                collection.add(obj.parent)


    def should_export_object(self, obj):
        if obj.type not in self.options.object_types:
            trace(f' - {obj.name}: Not exporting objects of type {obj.type}')
            return False
        if self.options.use_export_visible and obj.hide_get() or obj.hide_select:
            trace(f' - {obj.name}: Not visible')
            return False
        if self.options.use_export_selected and not obj.select_get():
            trace(f' - {obj.name}: Not selected')
            return False
        if self.options.use_active_layers:
            valid = True
            for col in obj.users_collection:
                if col.hide_viewport == True:
                    valid = False
                    break
                    
            if not valid:
                trace(f' - {obj.name}: Not visible in any user collections')
                return False

        trace(f' - {obj.name}: OK')
        return True
    


class DIVINITYEXPORTER_OT_export_collada(Operator, ExportHelper):
    """Export to Collada/GR2 with Divinity/Baldur's Gate-specific options (.dae/.gr2)"""
    bl_idname = "export_scene.dos2de_collada"
    bl_label = "Export Collada/GR2"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext: StringProperty(
        name="File Extension",
        options={"HIDDEN"},
        default=".dae"
    )

    filter_glob: StringProperty(default="*.dae;*.gr2", options={"HIDDEN"})
    
    filename: StringProperty(
        name="File Name",
        options={"HIDDEN"}
    )
    directory: StringProperty(
        name="Directory",
        options={"HIDDEN"}
    )

    export_directory: StringProperty(
        name="Project Export Directory",
        default="",
        options={"HIDDEN"}
    )

    use_metadata: BoolProperty(
        name="Use Metadata",
        default=True,
        options={"HIDDEN"}
        )

    auto_determine_path: BoolProperty(
        default=True,
        name="Auto-Path",
        description="Automatically determine the export path"
        )

    update_path: BoolProperty(
        default=False,
        options={"HIDDEN"}
        )
        
    auto_filepath: StringProperty(
        name="Auto Filepath",
        default="",
        options={"HIDDEN"}
        )     
        
    last_filepath: StringProperty(
        name="Last Filepath",
        default="",
        options={"HIDDEN"}
        )

    initialized: BoolProperty(default=False)
    update_path_next: BoolProperty(default=False)
    log_message: StringProperty(options={"HIDDEN"})

    def update_filepath(self, context):

        # JATO: This might be dumb
        addon_prefs = get_prefs(context)
        divine = DivineInvoker(addon_prefs, self.divine_settings)
        if divine.check_lslib() and addon_prefs.gr2_default_enabled:
            self.filename_ext = ".GR2"

        # JATO: Get the parent collection of the active object
        def get_active_collection_name(obj):
            for collection in bpy.data.collections:
                if obj.name in collection.objects:
                    return collection.name
            active_collection = bpy.context.view_layer.active_layer_collection.collection
            if active_collection is not None:
                return active_collection.name
            return None

        obj = bpy.context.active_object
        active_collection_name = get_active_collection_name(obj)

        if self.directory == "":
            self.directory = os.path.dirname(bpy.data.filepath)

        if active_collection_name != None:
            self.filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, active_collection_name, ".blend", ""), self.filename_ext)

        if self.filepath == "":
            self.filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, str.replace(bpy.path.basename(bpy.data.filepath), ".blend", "")), self.filename_ext)

        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath

        next_path = ""

        if self.filepath != "":
            if self.auto_name == "LAYER":
                if "namedlayers" in bpy.data.scenes[context.scene.name]:
                    namedlayers = getattr(bpy.data.scenes[context.scene.name], "namedlayers", None)
                    if namedlayers is not None:
                        #print("ACTIVE_LAYER: {}".format(context.scene.active_layer))
                        if (bpy.data.scenes[context.scene.name].layers[context.scene.active_layer]):
                                next_path = namedlayers.layers[context.scene.active_layer].name
                else:
                    self.log_message = "The 3D Layer Manager addon must be enabled before you can use layer names when exporting."
            elif self.auto_name == "ACTION":
                armature = None
                if self.use_active_layers:
                    obj = next(iter([x for x in context.scene.objects if x.type == "ARMATURE" and x.layers[context.scene.active_layer]]))
                    if obj is not None:
                        armature = obj
                elif self.use_export_selected:
                    for obj in context.scene.objects:
                        if obj.select_get() and obj.type == "ARMATURE":
                            armature = obj
                            break
                else:
                    for obj in context.scene.objects:
                        if obj.type == "ARMATURE":
                            armature = obj
                            break
                if armature is not None:
                    anim_name = (armature.animation_data.action.name
                            if armature.animation_data is not None and
                            armature.animation_data.action is not None
                            else "")
                    if anim_name != "":
                        next_path = anim_name
                    else:
                        #Blend name
                        next_path = str.replace(bpy.path.basename(bpy.data.filepath), ".blend", "")
            elif self.auto_name == "DISABLED" and self.last_filepath != "":
                self.auto_filepath = self.last_filepath

        if self.auto_determine_path == True and get_prefs(context).auto_export_subfolder == True and self.export_directory != "":
            auto_directory = self.export_directory
            if self.selected_preset != "NONE":
                if self.selected_preset == "MODEL":
                    if "_FX_" in next_path and os.path.exists("{}\\Models\\Effects".format(self.export_directory)):
                        auto_directory = "{}\\Models\\Effects".format(self.export_directory)
                    else:
                        auto_directory = "{}\\{}".format(self.export_directory, "Models")
                elif self.selected_preset == "ANIMATION":
                    auto_directory = "{}\\{}".format(self.export_directory, "Animations")
                elif self.selected_preset == "MESHPROXY":
                    auto_directory = "{}\\{}".format(self.export_directory, "Proxy")
            
            if not os.path.exists(auto_directory):
                os.mkdir(auto_directory)
            self.directory = auto_directory
            self.update_path = True
        
        #print("Dir export_directory({}) self.directory({})".format(self.export_directory, self.directory))

        if next_path != "":
            if self.selected_preset == "MESHPROXY":
                next_path = "Proxy_{}".format(next_path)
            self.auto_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, next_path), self.filename_ext)
            self.update_path = True

        return
 
    misc_settings_visible: BoolProperty(
        name="Misc Settings",
        default=False,
        options={"HIDDEN"}
    )

    extra_data_disabled: BoolProperty(
        name="Disable Extra Data",
        default=False
    )

    convert_gr2_options_visible: BoolProperty(
        name="GR2 Options",
        default=False,
        options={"HIDDEN"}
    )

    divine_settings: bpy.props.PointerProperty(
        type=Divine_ExportSettings,
        name="GR2 Settings"
    )

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling
    object_types: EnumProperty(
        name="Object Types",
        options={"ENUM_FLAG"},
        items=(
               ("ARMATURE", "Armature", ""),
               ("MESH", "Mesh", ""),
               ("CURVE", "Curve", ""),
        ),
        default={"ARMATURE", "MESH", "CURVE"}
    )

    use_export_selected: BoolProperty(
        name="Selected Only",
        description="Export only selected objects (and visible in active "
                    "layers if that applies)",
        default=False
        )

    use_export_visible: BoolProperty(
        name="Visible Only",
        description="Export only visible, unhidden, selectable objects",
        default=True
    )

    yup_rotation_options = (
        ("DISABLED", "Disabled", ""),
        ("ROTATE", "Rotate", "Rotate the object towards y-up"),
        ("ACTION", "Flag", "Flag the object as being y-up without rotating it")
    )

    auto_name: EnumProperty(
        name="Auto-Name",
        description="Auto-generate a filename based on a property name",
        items=(("DISABLED", "Disabled", ""),
               ("LAYER", "Layer Name", ""),
               ("ACTION", "Action Name", "")),
        default=("DISABLED"),
        update=update_filepath
        )
    use_mesh_modifiers: BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers to mesh objects (does not apply Armature modifier)",
        default=True
        )
    use_apply_pose_to_armature: BoolProperty(
        name="Apply Pose to Armature",
        description="Apply the current pose to the armature as a new Rest Pose",
        default=False
        )
    use_normalize_vert_groups: BoolProperty(
        name="Normalize Vertex Groups",
        description="Normalize all vertex groups",
        default=True
        )
    use_rest_pose: BoolProperty(
        name="Use Rest Pose on Mesh",
        description="Ignore pose from the Armature modifier on exported meshes",
        default=True
        )

    use_apply_shapekeys: BoolProperty(
        name="Apply Shapekeys",
        description="Apply shapekey transformation as visible within the 3D viewport",
        default=True
        )

    use_tangent: BoolProperty(
        name="Export Tangents",
        description="Export Tangent and Binormal arrays (for normalmapping)",
        default=True
        )
    use_triangles: BoolProperty(
        name="Triangulate",
        description="Convert all mesh faces to triangles",
        default=True
        )

    use_active_layers: BoolProperty(
        name="Active Layers Only",
        description="Export only objects on the active layers",
        default=True
        )
    use_exclude_ctrl_bones: BoolProperty(
        name="Exclude Control Bones",
        description=("Exclude skeleton bones with names beginning with 'ctrl' "
                     "or bones which are not marked as Deform bones"),
        default=False
        )
    use_anim: BoolProperty(
        name="Export Animation",
        description="Export keyframe animation",
        default=False
        )
    use_anim_action_all = BoolProperty(name="All Actions",
        description=("Export all actions for the first armature found in separate DAE files"),
        default=False
        )
    keep_copies: BoolProperty(
        name="(DEBUG) Keep Object Copies",
        default=False
        )

    applying_preset: BoolProperty(default=False)
    yup_local_override: BoolProperty(default=False)

    def yup_local_override_save(self, context):
        if self.applying_preset is not True:
            self.yup_local_override = True
            bpy.context.scene['dos2de_yup_local_override'] = self.yup_enabled

    yup_enabled: EnumProperty(
        name="Y-Up",
        description="Converts from Z-up to Y-up",
        items=yup_rotation_options,
        default=("ROTATE"),
        update=yup_local_override_save
        )

    # Used to reset the global extra flag when a preset is changed
    preset_applied_extra_flag: BoolProperty(default=False)
    preset_last_extra_flag: EnumProperty(items=gr2_extra_flags, default=("DISABLED"))
       
    def apply_preset(self, context):
        if self.initialized:
            #bpy.data.window_managers['dos2de_lastpreset'] = str(self.selected_preset)
            bpy.context.scene['dos2de_lastpreset'] = self.selected_preset
            self.applying_preset = True

        if self.selected_preset == "NONE":
            if self.preset_applied_extra_flag:
                if self.preset_last_extra_flag != "DISABLED":
                    self.divine_settings.gr2_settings.extras = self.preset_last_extra_flag
                    self.preset_last_extra_flag = "DISABLED"
                    print("Reverted extras flag to {}".format(self.divine_settings.gr2_settings.extras))
                else:
                    self.divine_settings.gr2_settings.extras = "DISABLED"
                self.preset_applied_extra_flag = False
            return
        elif self.selected_preset == "MODEL":
            self.object_types = {"ARMATURE", "MESH"}

            if self.yup_local_override is False:
                self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = True
            #self.use_rest_pose = True
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "LAYER"

            self.use_exclude_ctrl_bones = False
            self.use_anim = False

            if self.preset_applied_extra_flag:
                if self.preset_last_extra_flag != "DISABLED":
                    self.divine_settings.gr2_settings.extras = self.preset_last_extra_flag
                    self.preset_last_extra_flag = "DISABLED"
                    print("Reverted extras flag to {}".format(self.divine_settings.gr2_settings.extras))
                else:
                    self.divine_settings.gr2_settings.extras = "DISABLED"
                self.preset_applied_extra_flag = False

        elif self.selected_preset == "ANIMATION":
            self.object_types = {"ARMATURE"}
            if self.yup_local_override is False:
                self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = False
            self.use_rest_pose = False
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "ACTION"

            self.use_exclude_ctrl_bones = False
            self.use_anim = True

            if (self.preset_applied_extra_flag == False):
                if(self.preset_last_extra_flag == "DISABLED" and self.divine_settings.gr2_settings.extras != "DISABLED"):
                    self.preset_last_extra_flag = self.divine_settings.gr2_settings.extras
                self.preset_applied_extra_flag = True
            
            self.divine_settings.gr2_settings.extras = "DISABLED"

        elif self.selected_preset == "MESHPROXY":
            self.object_types = {"MESH"}
            if self.yup_local_override is False:
                self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = True
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "LAYER"

            self.use_exclude_ctrl_bones = False
            self.use_anim = False

            if (self.preset_applied_extra_flag == False):
                if(self.preset_last_extra_flag == "DISABLED" and self.divine_settings.gr2_settings.extras != "DISABLED"):
                    self.preset_last_extra_flag = self.divine_settings.gr2_settings.extras
                self.preset_applied_extra_flag = True
            
            self.divine_settings.gr2_settings.extras = "MESHPROXY"

        if self.initialized:
            self.update_path_next = True
        return
        #self.selected_preset = "NONE"

    selected_preset: EnumProperty(
        name="Preset",
        description="Use a built-in preset",
        items=(("NONE", "None", ""),
               ("MESHPROXY", "MeshProxy", "Use default meshproxy settings"),
               ("ANIMATION", "Animation", "Use default animation settings"),
               ("MODEL", "Model", "Use default model settings")),
        default=("NONE"),
        update=apply_preset
    )

    batch_mode: BoolProperty(
        name="Batch Export",
        description="Export all active layers as separate files, or every action as separate animation files",
        default=False
    )

    debug_mode: BoolProperty(default=False, options={"HIDDEN"})

    def draw(self, context):
        layout = self.layout
        
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "object_types")

        col = layout.column(align=True)
        col.prop(self, "auto_determine_path")
        col.prop(self, "selected_preset")
        if self.debug_mode:
            col.prop(self, "batch_mode")

        box = layout.box()
        box.prop(self, "auto_name")
        box.prop(self, "yup_enabled")

        box = layout.box()
        box.prop(self, "use_active_layers")
        box.prop(self, "use_export_visible")
        box.prop(self, "use_export_selected")

        box = layout.box()
        box.prop(self, "use_apply_shapekeys")
        box.prop(self, "use_mesh_modifiers")
        box.prop

        box = layout.box()
        box.prop(self, "use_apply_pose_to_armature")
        box.prop(self, "use_rest_pose")

        row = layout.row(align=True)
        row.prop(self, "use_normalize_vert_groups")
        
        row = layout.row(align=True)
        row.prop(self, "use_tangent")

        row = layout.row(align=True)
        row.prop(self, "use_triangles")

        box = layout.box()

        label = "Show GR2 Options" if not self.convert_gr2_options_visible else "Hide GR2 Options"
        box.prop(self, "convert_gr2_options_visible", text=label, toggle=True)

        if self.convert_gr2_options_visible:
            self.divine_settings.draw(context, box)

        col = layout.column(align=True)
        label = "Misc Settings" if not self.convert_gr2_options_visible else "Misc Settings"
        col.prop(self, "misc_settings_visible", text=label, toggle=True)
        if self.misc_settings_visible:
            box = layout.box()
            box.prop(self, "use_exclude_ctrl_bones")
            box.prop(self, "keep_copies")
            
    @property
    def check_extension(self):
        return True
    
    def check(self, context):
        self.applying_preset = False

        if self.log_message != "":
            print(self.log_message)
            report("{}".format(self.log_message), "WARNING")
            self.log_message = ""

        update = False

        if self.divine_settings.navigate_to_blendfolder == True:
            self.directory = os.path.dirname(bpy.data.filepath)
            self.filepath = "" #reset
            self.update_path_next = True
            self.divine_settings.navigate_to_blendfolder = False

        if(self.update_path_next):
            self.update_filepath(context)
            self.update_path_next = False
        
        if self.update_path:
            update = True
            self.update_path = False
            if self.filepath != self.auto_filepath:
                self.filepath = bpy.path.ensure_ext(self.auto_filepath, self.filename_ext)
                #print("[DOS2DE] Filepath is actually: " + self.filepath)

        return update
        

    def invoke(self, context, event):
        addon_prefs = get_prefs(context)

        blend_path = bpy.data.filepath
        #print("Blend path: {} ".format(blend_path))

        saved_preset = bpy.context.scene.get('dos2de_lastpreset', None)

        if saved_preset is not None:
            self.selected_preset = saved_preset
        else:
            if addon_prefs.default_preset != "NONE":
                self.selected_preset = addon_prefs.default_preset

        if "laughingleader_blender_helpers" in context.preferences.addons:
            helper_preferences = context.preferences.addons["laughingleader_blender_helpers"].preferences
            if helper_preferences is not None:
                self.debug_mode = getattr(helper_preferences, "debug_mode", False)
        #print("Preset: \"{}\"".format(self.selected_preset))

        scene_props = bpy.context.scene.ls_properties
        if scene_props.game != "unset":
            self.divine_settings.game = scene_props.game

        yup_local_override = bpy.context.scene.get('dos2de_yup_local_override', None)

        if yup_local_override is not None:
            self.yup_enabled = yup_local_override

        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath

        if addon_prefs.projects and self.auto_determine_path == True:
            projects = addon_prefs.projects.project_data
            if projects:
                for project in projects:
                    project_folder = project.project_folder
                    export_folder = project.export_folder

                    trace("Checking {} for {}".format(blend_path, project_folder))

                    if(export_folder != "" and project_folder != "" and 
                        bpy.path.is_subdir(blend_path, project_folder)):
                            self.export_directory = export_folder
                            self.directory = export_folder
                            self.filepath = export_folder
                            self.last_filepath = self.filepath
                            trace("Setting start path to export folder: \"{}\"".format(export_folder))
                            break

        self.update_filepath(context)
        context.window_manager.fileselect_add(self)

        self.initialized = True

        return {'RUNNING_MODAL'}


    def pose_apply(self, context, obj):
        trace(f"    - Apply pose to '{obj.name}'")
        last_active = getattr(bpy.context.scene.objects, "active", None)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.armature_apply()
        obj.select_set(False)
        bpy.context.view_layer.objects.active = last_active
    

    def transform_apply(self, obj, location=False, rotation=False, scale=False):
        trace(f"    - Apply transform on '{obj.name}'")
        last_active = getattr(bpy.context.scene.objects, "active", None)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)
        obj.select_set(False)
        bpy.context.view_layer.objects.active = last_active


    def copy_obj(self, context, obj, old_parent):
        copy = obj.copy()
        copy.use_fake_user = False
        trace(f" - Copy '{obj.name}' -> '{copy.name}'")

        data = getattr(obj, "data", None)
        if data != None:
            copy.data = data.copy()
            copy.data.use_fake_user = False
        
        export_props = getattr(obj, "llexportprops", None)
        if export_props is not None:
            copy.llexportprops.copy(export_props)
            copy.llexportprops.original_name = obj.name
            #copy.data.name = copy.llexportprops.export_name

        context.collection.objects.link(copy)

        if old_parent is not None and not self.objects_to_export.should_export(old_parent):
            report(f"Object '{obj.name}' has a parent '{old_parent.name}' that will not export. Please unparent it or adjust the parent so it will export.")

        return copy
    

    def validate_export_order(self, objects):
        has_order = False
        objects = {o for o in objects if o.type == "MESH"}
        for object in objects:
            if object.data.ls_properties.export_order != 0:
                has_order = True

        if has_order:
            objects = sorted(objects, key=lambda o: o.data.ls_properties.export_order)
            for i in range(1,len(objects)):
                if objects[i-1].data.ls_properties.export_order != i:
                    report("Export order issue at or near object " + objects[i-1].name, "ERROR");
                    report("Make sure that your export orders are consecutive (1, 2, ...) and there are no gaps in export order numbers", "ERROR");
                    return False

        return True


    def cancel(self, context):
        pass


    def execute(self, context):
        global current_operator
        try:
            current_operator = self
            return self.really_execute(context)
        finally:
            current_operator = None


    def make_copy_recursive(self, context, obj, copies, old_parent):
        copy = self.copy_obj(context, obj, old_parent)
        copies[obj.name] = copy

        if obj.parent is not None and not self.objects_to_export.should_export(obj.parent):
            report(f"Object '{copy.name}' has a parent '{obj.parent.name}' that will not export. Unparenting copy and preserving transform.")
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = copy
            copy.select_set(True)
            bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
            copy.select_set(False)
            bpy.context.view_layer.objects.active = None

            armature_mod = self.get_armature_modifier(copy)
            if armature_mod is not None:
                copy.modifiers.remove(armature_mod)

        for child in obj.children:
            if self.objects_to_export.should_export(child):
                self.make_copy_recursive(context, child, copies, obj)


    def apply_yup_transform(self, obj):
        trans_before = f"(x={degrees(obj.rotation_euler[0])}, y={degrees(obj.rotation_euler[1])}, z={degrees(obj.rotation_euler[2])})"
        obj.rotation_euler = (obj.rotation_euler.to_matrix() @ Matrix.Rotation(radians(-90), 3, 'X')).to_euler()
        trans_after = f"(x={degrees(obj.rotation_euler[0])}, y={degrees(obj.rotation_euler[1])}, z={degrees(obj.rotation_euler[2])})"
        trace(f"    - Rotate {obj.name} to y-up: {trans_before} -> {trans_after}")


    def get_armature_modifier(self, obj):
        armature_mods = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
        return armature_mods[0] if len(armature_mods) > 0 else None


    def reparent_armature(self, orig, obj):
        mod = self.get_armature_modifier(orig)
        if mod is not None:
            trace(f"    - Re-parenting armature from '{orig.parent.name}' to '{obj.parent.name}'")
            obj.modifiers.remove(self.get_armature_modifier(obj))
            new_mod = obj.modifiers.new(mod.name, "ARMATURE")
            new_mod.object = obj.parent
            new_mod.invert_vertex_group = mod.invert_vertex_group
            new_mod.use_bone_envelopes = mod.use_bone_envelopes
            new_mod.use_deform_preserve_volume = mod.use_deform_preserve_volume
            new_mod.use_multi_modifier = mod.use_multi_modifier
            new_mod.use_vertex_groups = mod.use_vertex_groups
            new_mod.vertex_group = mod.vertex_group


    def apply_modifiers(self, obj):
        self.transform_apply(obj, location=True, rotation=True, scale=True)

        modifiers = [mod for mod in obj.modifiers if mod.type != 'ARMATURE']
        # JATO: We should always proceed to get evaluated mesh with shapekeys, modifiers, and poses... right? So we filter for mesh object type
        # if len(modifiers) == 0:
        #     return
        if obj.type not in {'MESH'}:
            return

        trace(f"    - Apply modifiers on '{obj.name}'")
        if self.use_rest_pose:
            armature_poses = {arm.name: arm.pose_position for arm in bpy.data.armatures}
            for arm in bpy.data.armatures:
                arm.pose_position = "REST"

        # JATO: If Apply Modifiers is NOT selected we remove the modifiers before they are evaluated
        if not self.use_mesh_modifiers:
            for modifier in modifiers:
                obj.modifiers.remove(modifier)

        # JATO: If Apply Shapekeys is NOT selected we remove the shapekeys before they are evaluated
        if not self.use_apply_shapekeys:
            if obj.data.shape_keys:
                shape_keys = obj.data.shape_keys
                for i in range(len(shape_keys.key_blocks) -1, -1, -1):
                    bpy.data.shape_keys["ShapeKeys"].key_blocks.remove(shape_keys.key_blocks[i])

        old_mesh = obj.data
        dg = bpy.context.evaluated_depsgraph_get()
        object_eval = obj.evaluated_get(dg)
        # JATO: The commented line does not appear to get the evaluated mesh. Maybe I'm missing something, but line below should fix
        #mesh = obj.to_mesh(preserve_all_data_layers=True, depsgraph=dg).copy()
        mesh = bpy.data.meshes.new_from_object(object_eval)

        # JATO: Copy over ls_properties manually. mesh.ls_properties is read-only (?) so we do this
        for ls_props in old_mesh.ls_properties.keys():
            mesh.ls_properties[ls_props]=old_mesh.ls_properties[ls_props]

        # Reset poses
        if self.use_rest_pose:
            for arm in bpy.data.armatures.values():
                arm.pose_position = armature_poses[arm.name]

        '''
        # JATO: Commented this out because it causes a reference error when exporting without modifiers.
        This will leave modifiers on the object but as far as I can tell they're not evaluated so it doesn't matter
        '''
        #for modifier in modifiers:
            #obj.modifiers.remove(modifier)
        
        obj.data = mesh
        bpy.data.meshes.remove(old_mesh)


    def reparent_object(self, copies, orig, obj):
        if obj.parent.type == "ARMATURE" and self.objects_to_export.should_export(obj.parent):
            trace(f"    - Set parent of '{obj.name}' from '{orig.parent.name}' to '{copies[orig.parent.name].name}'")
            obj.parent = copies[orig.parent.name]
            self.reparent_armature(orig, obj)
        else:
            trace(f"    - Copy world transform and unparent from '{obj.parent.name}' to '{obj.name}")
            matrix_copy = obj.parent.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = matrix_copy


    def update_hierarchy(self, context, copies, orig, obj):
        trace(f" - Prepare '{orig.name}' -> '{obj.name}")

        if obj.type == "ARMATURE":
            if self.use_apply_pose_to_armature:
                self.pose_apply(context, obj)
            elif self.use_rest_pose:
                d = getattr(obj, "data", None)
                if d is not None:
                    d.pose_position = "REST"

        if obj.type == "MESH" and obj.parent is not None:
            self.reparent_object(copies, orig, obj)


    def apply_all_object_transforms(self, context, copies, orig, obj):
        trace(f" - Transform '{orig.name}' -> '{obj.name}")

        export_props = getattr(obj, "llexportprops", None)
        if export_props is not None:
            if not obj.parent:
                export_props.prepare(context, obj)
                for childobj in obj.children:
                    childobj.llexportprops.prepare(context, childobj)
                    childobj.llexportprops.prepare_name(context, childobj)
            export_props.prepare_name(context, obj)
        
        if self.yup_enabled == "ROTATE" and self.objects_to_export.is_root(orig):
            self.apply_yup_transform(obj)

        self.apply_modifiers(obj)

        if obj.type == "MESH" and obj.vertex_groups:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
            bpy.ops.object.vertex_group_limit_total(limit=4)
            bpy.ops.object.mode_set(mode="OBJECT")
            #trace("    - Limited total vertex influences to 4 for {}.".format(obj.name))
            obj.select_set(False)

            if self.use_normalize_vert_groups:
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
                bpy.ops.object.vertex_group_normalize_all()
                bpy.ops.object.mode_set(mode="OBJECT")
                #trace("    - Normalized vertex groups for {}.".format(obj.name))
                obj.select_set(False)


    def remove_copies(self, copies):
        bpy.ops.object.select_all(action='DESELECT')

        for obj in copies.values():
            if obj is not None:
                obj.select_set(True)

        bpy.ops.object.delete(use_global=True)

        #Cleanup
        for block in bpy.data.meshes:
            if block.users == 0:
                bpy.data.meshes.remove(block)

        for block in bpy.data.armatures:
            if block.users == 0:
                bpy.data.armatures.remove(block)

        for block in bpy.data.materials:
            if block.users == 0:
                bpy.data.materials.remove(block)

        for block in bpy.data.textures:
            if block.users == 0:
                bpy.data.textures.remove(block)

        for block in bpy.data.images:
            if block.users == 0:
                bpy.data.images.remove(block)
    

    def really_execute(self, context):
        output_path = Path(self.properties.filepath)
        if output_path.suffix.lower() == '.gr2':
            temp = tempfile.NamedTemporaryFile(delete=False)
            temp.close()
            tempfile_path = Path(temp.name)
            collada_path = tempfile_path
        else:
            tempfile_path = None
            collada_path = output_path

        result = ""
        
        addon_prefs = get_prefs(context)

        if bpy.context.object is not None and bpy.context.object.mode is not None:
            current_mode = bpy.context.object.mode
        else:
            current_mode = "OBJECT"

        activeObject = None
        if bpy.context.view_layer.objects.active:
            activeObject = bpy.context.view_layer.objects.active
        
        selectedObjects = []
        copies = {}

        if activeObject is not None and not activeObject.hide_get():
            bpy.ops.object.mode_set(mode="OBJECT")

        collector = ExportTargetCollector(self)
        self.objects_to_export = collector.collect(context.scene.objects)

        for obj in self.objects_to_export.ordered_targets:
            if obj.select_get():
                selectedObjects.append(obj)
                obj.select_set(False)

        if not self.validate_export_order(self.objects_to_export.ordered_targets):
            return {"FINISHED"}
        
        context.scene.ls_properties.metadata_version = ColladaMetadataLoader.LSLIB_METADATA_VERSION

        trace(f'Copying objects:')
        for obj in self.objects_to_export.ordered_targets:
            if obj.parent is None or not self.objects_to_export.should_export(obj.parent):
                self.make_copy_recursive(context, obj, copies, None)

        ordered_copies = []
        for obj in self.objects_to_export.ordered_targets:
            ordered_copies.append((obj, copies[obj.name]))

        trace(f'Preparing hierarchy:')
        # Update parents of copied objects before performing any modifications;
        # otherwise the transforms may not propagate to children properly
        for (orig, obj) in ordered_copies:
            self.update_hierarchy(context, copies, orig, obj)

        trace(f'Applying transforms:')
        for (orig, obj) in ordered_copies:
            self.apply_all_object_transforms(context, copies, orig, obj)

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "global_scale",
                                            "check_existing",
                                            "filter_glob",
                                            "xna_validate",
                                            "filepath"
                                            ))

        exported_pathways = []

        single_mode = self.batch_mode == False

        if self.batch_mode:
            if self.use_anim:
                single_mode = True
            else:
                if self.use_active_layers:
                    progress_total = len(list(i for i in range(20) if context.scene.layers[i]))
                    for i in range(20):
                        if context.scene.layers[i]:
                            export_list = list(filter(lambda orig, obj: obj.layers[i], ordered_copies))
                            export_name = "{}_Layer{}".format(bpy.path.basename(bpy.context.blend_data.filepath), i)

                            if self.auto_name == "LAYER" and "namedlayers" in bpy.data.scenes[context.scene.name]:
                                namedlayers = getattr(bpy.data.scenes[context.scene.name], "namedlayers", None)
                                if namedlayers is not None:
                                    export_name = namedlayers.layers[i].name
                            
                            export_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, export_name), self.filename_ext)
                            print("[DOS2DE-Exporter] Batch exporting layer '{}' as '{}'.".format(i, export_filepath))

                            if export_dae.save(self, context, export_list, filepath=export_filepath, **keywords) == {"FINISHED"}:
                                exported_pathways.append(export_filepath)
                            else:
                                report( "[DOS2DE-Exporter] Failed to export '{}'.".format(export_filepath))
                else:
                    single_mode = True

        if single_mode:
            result = export_dae.save(self, context, copies.values(), filepath=str(collada_path), **keywords)
            if result == {"FINISHED"}:
                exported_pathways.append(str(collada_path))

        if not self.keep_copies:
            self.remove_copies(copies)

        bpy.ops.object.select_all(action='DESELECT')
        
        for obj in selectedObjects:
            obj.select_set(True)
        
        if activeObject is not None:
            bpy.context.view_layer.objects.active = activeObject
        
        # Return to previous mode
        try:
            if current_mode is not None and activeObject is not None and not activeObject.hide_get():
                if activeObject.type != "ARMATURE" and current_mode == "POSE":
                    bpy.ops.object.mode_set(mode="OBJECT")
                else:
                    bpy.ops.object.mode_set(mode=current_mode)
        except Exception as e:
            print("[DOS2DE-Collada] Error setting viewport mode:\n{}".format(e))

        if tempfile_path is not None:
            divine = DivineInvoker(addon_prefs, self.divine_settings)
            for collada_file in exported_pathways:
                divine.dae_to_gr2(str(tempfile_path), str(output_path))
            tempfile_path.unlink()

        report("Export completed successfully.", "INFO")
        return {"FINISHED"}

addon_keymaps = []

added_export_options = False

class LSMeshProperties(PropertyGroup):
    rigid: BoolProperty(
        name="Rigid",
        default = False
        )
    cloth: BoolProperty(
        name="Cloth",
        default = False
        )
    mesh_proxy: BoolProperty(
        name="Mesh Proxy",
        default = False
        )
    proxy: BoolProperty(
        name="Proxy Geometry",
        default = False
        )
    spring: BoolProperty(
        name="Spring",
        default = False
        )
    occluder: BoolProperty(
        name="Occluder",
        default = False
        )
    impostor: BoolProperty(
        name="Impostor",
        default = False
        )
    cloth_physics: BoolProperty(
        name="Cloth Physics",
        default = False
        )
    cloth_flag1: BoolProperty(
        name="Cloth Flag 1",
        default = False
        )
    cloth_flag2: BoolProperty(
        name="Cloth Flag 2",
        default = False
        )
    cloth_flag4: BoolProperty(
        name="Cloth Flag 4",
        default = False
        )
    export_order: IntProperty(
        name="Export Order",
        min = 0,
        max = 100,
        default = 0
        )
    lod: IntProperty(
        name="LOD Level",
        description="Lower LOD value = more detailed mesh",
        min = 0,
        max = 10,
        default = 0
        )
    lod_distance: FloatProperty(
        name="LOD Distance",
        description="Distance (in meters) after which the next LOD level is displayed",
        min = 0.0,
        default = 0.0
        )

class LSArmatureProperties(PropertyGroup):
    skeleton_resource_id: StringProperty(
        name="Skeleton Resource UUID",
        default = ""
        )

class LSBoneProperties(PropertyGroup):
    export_order: IntProperty(
        name="Export Order",
        description="Index of bone in the exported .GR2 file; must match bone order of the reference skeleton",
        default = 0
        )

class LSSceneProperties(PropertyGroup):
    game: EnumProperty(
        name="Game",
        description="The target game. Currently determines the model format type",
        items=game_versions,
        default=("bg3")
    )
    metadata_version: IntProperty(
        name="Metadata Version",
        options={"HIDDEN"},
        default=0
    )

class OBJECT_PT_LSPropertyPanel(Panel):
    bl_label = "BG3 Settings"
    bl_idname = "OBJECT_PT_ls_property_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    
    def draw(self, context):
        layout = self.layout
        if context.active_object.type == "MESH":
            props = context.active_object.data.ls_properties

            box = layout.box()
            box.label(text="Mesh Type")

            row = box.grid_flow()
            row.prop(props, "rigid")
            row.prop(props, "cloth")
            row.prop(props, "mesh_proxy")
            row.prop(props, "proxy")
            row.prop(props, "spring")
            row.prop(props, "occluder")
            row.prop(props, "impostor")
            row.prop(props, "cloth_physics")
            row.prop(props, "cloth_flag1")
            row.prop(props, "cloth_flag2")
            row.prop(props, "cloth_flag4")

            layout.prop(props, "lod")
            layout.prop(props, "lod_distance")
            layout.prop(props, "export_order")
        elif context.active_object.type == "ARMATURE":
            props = context.active_object.data.ls_properties
            layout.prop(props, "skeleton_resource_id")


class BONE_PT_LSPropertyPanel(Panel):
    bl_label = "DOS2/BG3 Settings"
    bl_idname = "BONE_PT_ls_property_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "bone"
    
    def draw(self, context):
        layout = self.layout
        props = context.active_bone.ls_properties
        layout.prop(props, "export_order")


class SCENE_PT_LSPropertyPanel(Panel):
    bl_label = "DOS2/BG3 Settings"
    bl_idname = "SCENE_PT_ls_property_panel"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "scene"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.ls_properties
        layout.prop(props, "game")



class ColladaMetadataLoader:
    root = None
    armature = None
    SCHEMA = "{http://www.collada.org/2005/11/COLLADASchema}"
    LSLIB_METADATA_VERSION = 3

    TAG_TO_GAME = {
        "DivinityOriginalSin": "dos",
        "DivinityOriginalSinEE": "dosee",
        "DivinityOriginalSin2": "dos2",
        "DivinityOriginalSin2DE": "dos2de",
        "BaldursGate3PrePatch8": "bg3",
        "BaldursGate3": "bg3",
        "Unset": "unset",
    }

    def load_root_profile(self, context):
        profile = self.root.find(f"./{self.SCHEMA}extra/{self.SCHEMA}technique[@profile='LSTools']")
        if profile is None:
            report("LSLib profile data not found in Collada export; make sure you're using LSLib v1.16 or later!", "ERROR")
            return
        
        meta_version = 0
        
        props = context.scene.ls_properties
        for ele in list(profile):
            _, _, tag = ele.tag.rpartition('}')
            if tag == 'Game':
                props.game = self.TAG_TO_GAME[ele.text]
            elif tag == 'MetadataVersion':
                meta_version = int(ele.text)

        if meta_version < self.LSLIB_METADATA_VERSION:
            report("Collada file was exported with a too old LSLib version, important metadata might be missing! Please upgrade your LSLib!", "ERROR")

        if meta_version > self.LSLIB_METADATA_VERSION:
            report("The Blender exporter plugin is too old for this LSLib version, please upgrade your exporter plugin!", "ERROR")


    def find_anim_settings(self):
        for anim in self.root.findall(f"./{self.SCHEMA}library_animations/{self.SCHEMA}animation"):
            settings = anim.find(f"{self.SCHEMA}extra/{self.SCHEMA}technique[@profile='LSTools']")
            if settings is not None:
                return settings

        return None
    
    def load_mesh_profile(self, geom, settings):
        if geom.attrib['name'] not in bpy.data.objects:
            report("Couldnt load metadata on geometry '" + geom.attrib['name'] + "' (object not found)", "ERROR")
            return
        
        mesh = bpy.data.objects[geom.attrib['name']].data
        props = mesh.ls_properties
        for ele in list(settings):
            _, _, tag = ele.tag.rpartition('}')
            if tag == 'DivModelType':
                if ele.text == 'Rigid':
                    props.rigid = True
                elif ele.text == 'Cloth':
                    props.cloth = True
                elif ele.text == 'MeshProxy':
                    props.mesh_proxy = True
                elif ele.text == 'ProxyGeometry':
                    props.proxy = True
                elif ele.text == 'Spring':
                    props.spring = True
                elif ele.text == 'Occluder':
                    props.occluder = True
                elif ele.text == 'ClothPhysics':
                    props.cloth_physics = True
                elif ele.text == 'Cloth01':
                    props.cloth_flag1 = True
                elif ele.text == 'Cloth02':
                    props.cloth_flag2 = True
                elif ele.text == 'Cloth04':
                    props.cloth_flag4 = True
                else:
                    report("Unrecognized DivModelType in mesh profile: " + ele.text)
            elif tag == 'IsImpostor' and ele.text == '1':
                props.impostor = True
            elif tag == 'ExportOrder':
                props.export_order = int(ele.text) + 1
            elif tag == 'LOD':
                props.lod = int(ele.text)
            elif tag == 'LODDistance':
                props.lod_distance = float(ele.text)
            else:
                report("Unrecognized attribute in mesh profile: " + tag)
    
    def load_mesh_profiles(self):
        for geom in self.root.findall(f"./{self.SCHEMA}library_geometries/{self.SCHEMA}geometry"):
            settings = geom.find(f"{self.SCHEMA}mesh/{self.SCHEMA}extra/{self.SCHEMA}technique[@profile='LSTools']")
            if settings is not None:
                self.load_mesh_profile(geom, settings)
    
    def load_bone_profile(self, bone, settings):
        bones = [b for b in self.armature.data.bones if b.name == bone.attrib['name']] 
        if len(bones) == 0:
            report("Couldnt load metadata on bone '" + bone.attrib['name'] + "' (object not found)", "ERROR")
            return
        
        bone = bones[0]
        props = bone.ls_properties
        for ele in list(settings):
            _, _, tag = ele.tag.rpartition('}')
            if tag == 'BoneIndex':
                props.export_order = int(ele.text) + 1
            else:
                report("Unrecognized attribute in bone profile: " + tag)
    
    def load_bone_profiles(self, bone):
        for child in bone:
            if child.tag == f"{self.SCHEMA}node":
                self.load_bone_profiles(child)

        if 'type' in bone.attrib and bone.attrib['type'] == 'JOINT':
            settings = bone.find(f"{self.SCHEMA}extra/{self.SCHEMA}technique[@profile='LSTools']")
            if settings is not None:
                self.load_bone_profile(bone, settings)
    
    def load_armature_profiles(self):
        for scene in self.root.findall(f"./{self.SCHEMA}library_visual_scenes/{self.SCHEMA}visual_scene"):
            for ele in scene:
                if ele.tag == f"{self.SCHEMA}node":
                    self.load_bone_profiles(ele)

    def load_anim_profile(self, context, anim_settings):
        skel = anim_settings.find('SkeletonResourceID')
        skeleton_id = ""
        if skel is not None:
            skeleton_id = skel.text

        for obj in context.scene.objects:
            if obj.type == "ARMATURE" and obj.select_get():
                props = obj.data.ls_properties
                props.skeleton_resource_id = skeleton_id
    
    def load(self, context, collada_path):
        for obj in context.scene.objects:
            if obj.select_get() and obj.type == 'ARMATURE':
                self.armature = obj
                break

        self.root = et.parse(collada_path).getroot()
        self.load_root_profile(context)
        anim_settings = self.find_anim_settings()
        self.load_mesh_profiles()
        self.load_armature_profiles()
        if anim_settings is not None:
            self.load_anim_profile(context, anim_settings)



class DIVINITYEXPORTER_OT_import_collada(Operator, ImportHelper):
    """Import Divinity/Baldur's Gate models (Collada/GR2)"""
    bl_idname = "import_scene.dos2de_collada"
    bl_label = "Import Collada/GR2"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext: StringProperty(
        name="File Extension",
        options={"HIDDEN"},
        default=".dae"
    )

    filter_glob: StringProperty(default="*.dae;*.gr2", options={"HIDDEN"})

    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty()

    def fixup_bones(self, context):
        for obj in context.scene.objects:
            if obj.type == "ARMATURE" and obj.select_get():
                context.view_layer.objects.active = obj
                bpy.ops.object.mode_set(mode='EDIT')
                for bone in obj.data.edit_bones:
                    if len(bone.children) == 1:
                        bone.tail = bone.children[0].head
                    elif len(bone.children) == 0 and bone.parent is not None and len(bone.parent.children) == 1:
                        bone.use_connect = True
                bpy.ops.object.mode_set(mode='OBJECT')

        
    def execute(self, context):
        global current_operator
        try:
            current_operator = self
            return self.really_execute(context)
        finally:
            current_operator = None

    def really_execute(self, context):
        directory = self.directory

        for f in self.files:
            input_path = Path(os.path.join(directory, f.name))
            tempfile_path = None

            if input_path.suffix.lower() == '.gr2':
                addon_prefs = get_prefs(context)
                divine = DivineInvoker(addon_prefs, None)
                temp = tempfile.NamedTemporaryFile(delete=False)
                temp.close()
                tempfile_path = Path(temp.name)
                collada_path = tempfile_path
                if not divine.gr2_to_dae(str(input_path), str(collada_path)):
                    return{'CANCELLED'}
            else:
                collada_path = input_path

            if bpy.app.version >= (3, 4, 0):
                bpy.ops.wm.collada_import(filepath=str(collada_path), custom_normals=True, fix_orientation=True)
            else:
                bpy.ops.wm.collada_import(filepath=str(collada_path), fix_orientation=True)

            meta_loader = ColladaMetadataLoader()
            meta_loader.load(context, str(collada_path))
            self.fixup_bones(context)

            if tempfile_path is not None:
                tempfile_path.unlink()
            
            imported = context.selected_objects
            collection = bpy.data.collections.new(os.path.splitext(f['name'])[0])
            bpy.context.scene.collection.children.link(collection)
            for f in imported:
                for parent in f.users_collection:
                        parent.objects.unlink(f)
                collection.objects.link(f)

            report("Import completed successfully.", "INFO")
        return {'FINISHED'}

def export_menu_func(self, context):
    self.layout.operator(DIVINITYEXPORTER_OT_export_collada.bl_idname, text="DOS2/BG3 Collada (.dae, .gr2)")

def import_menu_func(self, context):
    self.layout.operator(DIVINITYEXPORTER_OT_import_collada.bl_idname, text="DOS2/BG3 Collada (.dae, .gr2)")

classes = (
    ProjectData,
    ProjectEntry,
    GR2_ExportSettings,
    Divine_ExportSettings,
    DIVINITYEXPORTER_OT_export_collada,
    DIVINITYEXPORTER_OT_import_collada,
    DIVINITYEXPORTER_OT_add_project,
    DIVINITYEXPORTER_OT_remove_project,
    DIVINITYEXPORTER_UL_project_list,
    DIVINITYEXPORTER_AddonPreferences,
    LSMeshProperties,
    LSArmatureProperties,
    LSBoneProperties,
    LSSceneProperties,
    OBJECT_PT_LSPropertyPanel,
    BONE_PT_LSPropertyPanel,
    SCENE_PT_LSPropertyPanel
)

def register():
    bpy.types.TOPBAR_MT_file_export.append(export_menu_func)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)

    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Mesh.ls_properties = PointerProperty(type=LSMeshProperties)
    bpy.types.Armature.ls_properties = PointerProperty(type=LSArmatureProperties)
    bpy.types.Bone.ls_properties = PointerProperty(type=LSBoneProperties)
    bpy.types.Scene.ls_properties = PointerProperty(type=LSSceneProperties)

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new('Window', space_type='EMPTY', region_type='WINDOW', modal=False)

    km_export = km.keymap_items.new(DIVINITYEXPORTER_OT_export_collada.bl_idname, 'E', 'PRESS', ctrl=True, shift=True)
    km_import = km.keymap_items.new(DIVINITYEXPORTER_OT_import_collada.bl_idname, 'I', 'PRESS', ctrl=True, shift=True)
    addon_keymaps.append((km, km_export))
    addon_keymaps.append((km, km_import))


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(export_menu_func)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)

    for cls in classes:
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.ls_properties
    del bpy.types.Bone.ls_properties
    del bpy.types.Armature.ls_properties
    del bpy.types.Mesh.ls_properties

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()
