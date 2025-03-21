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
    if "collada" in locals():
        importlib.reload(collada) # noqa
    if "divine" in locals():
        importlib.reload(divine) # noqa
    if "export_dae" in locals():
        importlib.reload(export_dae) # noqa
    if "gltf" in locals():
        importlib.reload(gltf) # noqa
    if "helpers" in locals():
        importlib.reload(helpers) # noqa
    if "operators_dae" in locals():
        importlib.reload(operators_dae) # noqa
    if "properties" in locals():
        importlib.reload(properties) # noqa

import bpy
from bpy.types import Operator, AddonPreferences, PropertyGroup, UIList, Panel
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty, CollectionProperty, PointerProperty, IntProperty

from . import export_dae, gltf, properties, helpers, operators_dae

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



def export_menu_func(self, context):
    self.layout.operator(operators_dae.DIVINITYEXPORTER_OT_export_collada.bl_idname, text="(DEPRECATED) DOS2/BG3 Collada (.dae, .gr2)")
    #self.layout.operator(DIVINITYEXPORTER_OT_export_gr2.bl_idname, text="DOS2/BG3 Granny (.gr2)")

def import_menu_func(self, context):
    self.layout.operator(operators_dae.DIVINITYEXPORTER_OT_import_collada.bl_idname, text="(DEPRECATED) DOS2/BG3 Collada (.dae, .gr2)")
    #self.layout.operator(DIVINITYEXPORTER_OT_impor_gr2.bl_idname, text="DOS2/BG3 Granny (.gr2)")


# Need to reexport these classes as the glTF exporter looks for these exact class names in the root module
glTF2ExportUserExtension = gltf.glTF2ExportUserExtension
glTF2ImportUserExtension = gltf.glTF2ImportUserExtension


addon_keymaps = []

classes = (
    ProjectData,
    ProjectEntry,
    DIVINITYEXPORTER_OT_add_project,
    DIVINITYEXPORTER_OT_remove_project,
    DIVINITYEXPORTER_UL_project_list,
    DIVINITYEXPORTER_AddonPreferences
)

def register():
    bpy.types.TOPBAR_MT_file_export.append(export_menu_func)
    bpy.types.TOPBAR_MT_file_import.append(import_menu_func)

    for cls in classes:
        bpy.utils.register_class(cls)

    properties.register()
    operators_dae.register()

    #wm = bpy.context.window_manager
    #km = wm.keyconfigs.addon.keymaps.new('Window', space_type='EMPTY', region_type='WINDOW', modal=False)

    #km_export = km.keymap_items.new(DIVINITYEXPORTER_OT_export_collada.bl_idname, 'E', 'PRESS', ctrl=True, shift=True)
    #km_import = km.keymap_items.new(DIVINITYEXPORTER_OT_import_collada.bl_idname, 'I', 'PRESS', ctrl=True, shift=True)
    #addon_keymaps.append((km, km_export))
    #addon_keymaps.append((km, km_import))


def unregister():
    bpy.types.TOPBAR_MT_file_export.remove(export_menu_func)
    bpy.types.TOPBAR_MT_file_import.remove(import_menu_func)

    for cls in classes:
        bpy.utils.unregister_class(cls)

    properties.unregister()
    operators_dae.unregister()

    #wm = bpy.context.window_manager
    #kc = wm.keyconfigs.addon
    #if kc:
    #    for km, kmi in addon_keymaps:
    #        km.keymap_items.remove(kmi)
    #addon_keymaps.clear()
