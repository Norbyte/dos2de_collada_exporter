from bpy.types import Operator, PropertyGroup
from bpy.props import StringProperty, BoolProperty, EnumProperty, PointerProperty, CollectionProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.utils import register_class, unregister_class

from math import radians, degrees
from mathutils import Matrix

from . import export_dae, properties, helpers, collada, divine

import bpy
import os
import tempfile
from pathlib import Path


gr2_extra_flags = (
    ("DISABLED", "Disabled", ""),
    ("MESHPROXY", "MeshProxy", "Flags the mesh as a meshproxy, used for displaying overlay effects on a weapon and AllSpark MeshEmiters"),
    ("CLOTH", "Cloth", "The mesh has vertex painting for use with Divinity's cloth system"),
    ("RIGID", "Rigid", "For meshes lacking an armature modifier. Typically used for weapons"),
    ("RIGIDCLOTH", "Rigid&Cloth", "For meshes lacking an armature modifier that also contain cloth physics. Typically used for weapons")
)


def get_prefs(context):
    return context.preferences.addons[__package__].preferences


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

    def draw(self, context, obj):
        obj.label(text="GR2 Options")
        obj.prop(self, "yup_conversion")

        obj.label(text="Extra Properties (Global)")
        obj.prop(self, "extras")
        #extrasobj = obj.row(align=False)
        #self.extras.draw(context, extrasobj)


class Divine_ExportSettings(PropertyGroup):
    """Divine GR2 Conversion Settings"""
    gr2_settings: PointerProperty(
        type=GR2_ExportSettings,
        name="GR2 Export Options"
    )

    game: EnumProperty(
        name="Game",
        description="The target game. Currently determines the model format type",
        items=properties.game_versions,
        default=("bg3")
    )

    ignore_uv_nan: BoolProperty(
        name="Ignore Bad NaN UVs",
        description="Ignore bad/unwrapped UVs that fail to form a triangle. Export will fail if these are detected",
        default=False
    )

    x_flip_meshes: BoolProperty(
        name="Flip meshes on X axis",
        description="BG3/DOS2 meshes are usually x-flipped in the GR2 file",
        default=False
    )

    mirror_skeletons: BoolProperty(
        name="Mirror Skeletons",
        description="Mirror left (_l) and right (_r) bones in the skeleton",
        default=False
    )

    keep_bind_info: BoolProperty(
		name="Keep Bind Info",
		description="Store Bindpose information in custom bone properties for later use during Collada export",
		default=True)

    navigate_to_blendfolder: BoolProperty(default=False)

    drawable_props = [
        "ignore_uv_nan",
        "x_flip_meshes",
        "mirror_skeletons"
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


class Divine_ImportSettings(PropertyGroup):
    """Divine GR2 Import Settings"""
    x_flip_meshes: BoolProperty(
        name="Flip meshes on X axis",
        description="BG3/DOS2 meshes are usually x-flipped in the GR2 file",
        default=False
    )

    mirror_skeletons: BoolProperty(
        name="Mirror Skeletons",
        description="Mirror left (_l) and right (_r) bones in the skeleton",
        default=False
    )

    def draw(self, context, obj):
        obj.label(text="GR2 Import Options")
        obj.prop(self, "x_flip_meshes")
        obj.prop(self, "mirror_skeletons")


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
        helpers.trace(f'Collecting objects to export:')
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
            helpers.trace(f' - {obj.name}: Marked for export because a parent will export')
            collection.add(obj)
            self.add_objects_recursive(obj.children, collection)


    def collect_parents(self, collection: ExportTargetCollection):
        for obj in list(collection.targets.values()):
            if obj.parent is not None and not collection.should_export(obj.parent) and obj.parent.type == "ARMATURE":
                helpers.trace(f' - {obj.parent.name}: Marked for export because a child with armature modifier will export')
                collection.add(obj.parent)


    def should_export_object(self, obj):
        if obj.type not in self.options.object_types:
            helpers.trace(f' - {obj.name}: Not exporting objects of type {obj.type}')
            return False
        if self.options.use_export_visible and obj.hide_get() or obj.hide_select:
            helpers.trace(f' - {obj.name}: Not visible')
            return False
        if self.options.use_export_selected and not obj.select_get():
            helpers.trace(f' - {obj.name}: Not selected')
            return False
        if self.options.use_active_layers:
            valid = True
            for col in obj.users_collection:
                if col.hide_viewport == True:
                    valid = False
                    break
                    
            if not valid:
                helpers.trace(f' - {obj.name}: Not visible in any user collections')
                return False

        helpers.trace(f' - {obj.name}: OK')
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
        invoker = divine.DivineInvoker(addon_prefs, self.divine_settings)
        if invoker.check_lslib() and addon_prefs.gr2_default_enabled:
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

    divine_settings: PointerProperty(
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
    use_apply_shapekeys: BoolProperty(
        name="Apply Shapekeys",
        description="Apply shapekey transformation as visible within the 3D viewport",
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
            helpers.report("{}".format(self.log_message), "WARNING")
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

                    helpers.trace("Checking {} for {}".format(blend_path, project_folder))

                    if(export_folder != "" and project_folder != "" and 
                        bpy.path.is_subdir(blend_path, project_folder)):
                            self.export_directory = export_folder
                            self.directory = export_folder
                            self.filepath = export_folder
                            self.last_filepath = self.filepath
                            helpers.trace("Setting start path to export folder: \"{}\"".format(export_folder))
                            break

        self.update_filepath(context)
        context.window_manager.fileselect_add(self)

        self.initialized = True

        return {'RUNNING_MODAL'}


    def pose_apply(self, context, obj):
        helpers.trace(f"    - Apply pose to '{obj.name}'")
        last_active = getattr(bpy.context.scene.objects, "active", None)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.armature_apply()
        obj.select_set(False)
        bpy.context.view_layer.objects.active = last_active
    

    def transform_apply(self, obj, location=False, rotation=False, scale=False):
        helpers.trace(f"    - Apply transform on '{obj.name}'")
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
        helpers.trace(f" - Copy '{obj.name}' -> '{copy.name}'")

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
            helpers.report(f"Object '{obj.name}' has a parent '{old_parent.name}' that will not export. Please unparent it or adjust the parent so it will export.")

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
                    helpers.report("Export order issue at or near object " + objects[i-1].name, "ERROR");
                    helpers.report("Make sure that your export orders are consecutive (1, 2, ...) and there are no gaps in export order numbers", "ERROR");
                    return False

        return True


    def cancel(self, context):
        pass


    def execute(self, context):
        try:
            helpers.current_operator = self
            return self.really_execute(context)
        finally:
            helpers.current_operator = None


    def make_copy_recursive(self, context, obj, copies, old_parent):
        copy = self.copy_obj(context, obj, old_parent)
        copies[obj.name] = copy

        if obj.parent is not None and not self.objects_to_export.should_export(obj.parent):
            helpers.report(f"Object '{copy.name}' has a parent '{obj.parent.name}' that will not export. Unparenting copy and preserving transform.")
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
        helpers.trace(f"    - Rotate {obj.name} to y-up: {trans_before} -> {trans_after}")


    def get_armature_modifier(self, obj):
        armature_mods = [mod for mod in obj.modifiers if mod.type == "ARMATURE"]
        return armature_mods[0] if len(armature_mods) > 0 else None


    def reparent_armature(self, orig, obj):
        mod = self.get_armature_modifier(orig)
        if mod is not None:
            helpers.trace(f"    - Re-parenting armature from '{orig.parent.name}' to '{obj.parent.name}'")
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
        
        helpers.trace(f"    - Apply modifiers on '{obj.name}'")
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
            helpers.trace(f"    - Set parent of '{obj.name}' from '{orig.parent.name}' to '{copies[orig.parent.name].name}'")
            obj.parent = copies[orig.parent.name]
            self.reparent_armature(orig, obj)
        else:
            helpers.trace(f"    - Copy world transform and unparent from '{obj.parent.name}' to '{obj.name}")
            matrix_copy = obj.parent.matrix_world.copy()
            obj.parent = None
            obj.matrix_world = matrix_copy


    def update_hierarchy(self, context, copies, orig, obj):
        helpers.trace(f" - Prepare '{orig.name}' -> '{obj.name}")

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
        helpers.trace(f" - Transform '{orig.name}' -> '{obj.name}")

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
            #helpers.trace("    - Limited total vertex influences to 4 for {}.".format(obj.name))
            obj.select_set(False)

            if self.use_normalize_vert_groups:
                bpy.context.view_layer.objects.active = obj
                obj.select_set(True)
                bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
                bpy.ops.object.vertex_group_normalize_all()
                bpy.ops.object.mode_set(mode="OBJECT")
                #helpers.trace("    - Normalized vertex groups for {}.".format(obj.name))
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
        
        context.scene.ls_properties.metadata_version = collada.ColladaMetadataLoader.LSLIB_METADATA_VERSION

        helpers.trace(f'Copying objects:')
        for obj in self.objects_to_export.ordered_targets:
            if obj.parent is None or not self.objects_to_export.should_export(obj.parent):
                self.make_copy_recursive(context, obj, copies, None)

        ordered_copies = []
        for obj in self.objects_to_export.ordered_targets:
            ordered_copies.append((obj, copies[obj.name]))

        helpers.trace(f'Preparing hierarchy:')
        # Update parents of copied objects before performing any modifications;
        # otherwise the transforms may not propagate to children properly
        for (orig, obj) in ordered_copies:
            self.update_hierarchy(context, copies, orig, obj)

        helpers.trace(f'Applying transforms:')
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
                                helpers.report( "[DOS2DE-Exporter] Failed to export '{}'.".format(export_filepath))
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
            invoker = divine.DivineInvoker(addon_prefs, self.divine_settings)
            for collada_file in exported_pathways:
                if not invoker.export_gr2(str(tempfile_path), str(output_path), "dae"):
                    return {"CANCELLED"}
            tempfile_path.unlink()

        helpers.report("Export completed successfully.", "INFO")
        return {"FINISHED"}



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
        try:
            helpers.current_operator = self
            return self.really_execute(context)
        finally:
            helpers.current_operator = None

    def really_execute(self, context):
        directory = self.directory

        for f in self.files:
            input_path = Path(os.path.join(directory, f.name))
            tempfile_path = None

            if input_path.suffix.lower() == '.gr2':
                addon_prefs = get_prefs(context)
                invoker = divine.DivineInvoker(addon_prefs, None)
                temp = tempfile.NamedTemporaryFile(delete=False)
                temp.close()
                tempfile_path = Path(temp.name)
                collada_path = tempfile_path
                if not invoker.import_gr2(str(input_path), str(collada_path), "dae"):
                    return{'CANCELLED'}
            else:
                collada_path = input_path

            if bpy.app.version >= (3, 4, 0):
                bpy.ops.wm.collada_import(filepath=str(collada_path), custom_normals=True, fix_orientation=True)
            else:
                bpy.ops.wm.collada_import(filepath=str(collada_path), fix_orientation=True)

            meta_loader = collada.ColladaMetadataLoader()
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

            helpers.report("Import completed successfully.", "INFO")
        return {'FINISHED'}


classes = (
    GR2_ExportSettings,
    Divine_ExportSettings,
    Divine_ImportSettings,
    DIVINITYEXPORTER_OT_export_collada,
    DIVINITYEXPORTER_OT_import_collada
)

def register():
    for cls in classes:
        register_class(cls)


def unregister():
    for cls in classes:
        unregister_class(cls)
