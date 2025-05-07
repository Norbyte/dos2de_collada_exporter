from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, PointerProperty, CollectionProperty
from bpy_extras.io_utils import ExportHelper, ImportHelper
from bpy.utils import register_class, unregister_class

from . import operators_dae, helpers, collada, divine

import bpy
import os
import tempfile
from pathlib import Path


def get_prefs(context):
    return context.preferences.addons[__package__].preferences


class DIVINITYEXPORTER_OT_export_gltf(Operator, ExportHelper):
    """Export to glTF/GR2 with Divinity/Baldur's Gate-specific options (.gr2)"""
    bl_idname = "export_scene.dos2de_gltf"
    bl_label = "Export glTF/GR2"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext: StringProperty(
        name="File Extension",
        options={"HIDDEN"},
        default=".gr2"
    )

    filter_glob: StringProperty(default="*.gr2", options={"HIDDEN"})
    
    filename: StringProperty(
        name="File Name",
        options={"HIDDEN"}
    )
    directory: StringProperty(
        name="Directory",
        options={"HIDDEN"}
    )

    initialized: BoolProperty(default=False)
    log_message: StringProperty(options={"HIDDEN"})

    divine_settings: PointerProperty(
        type=operators_dae.Divine_ExportSettings,
        name="GR2 Settings"
    )

    use_selection: BoolProperty(
        name="Selected Objects",
        description="Export selected objects only",
        default=False
    )

    use_visible: BoolProperty(
        name="Visible Objects",
        description="Export visible objects only",
        default=False
    )
    
    use_renderable: BoolProperty(
        name="Renderable Objects",
        description="Export renderable objects only",
        default=False
    )
    
    use_active_collection: BoolProperty(
        name="Active Collection",
        description="Export objects in the active collection only",
        default=False
    )
    
    use_active_scene: BoolProperty(
        name="Active Scene",
        description="Export active scene only",
        default=False
    )
    
    export_apply: BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers (excluding Armatures) to mesh objects - WARNING: prevents exporting shape keys",
        default=False
    )

    def draw(self, context):
        layout = self.layout

        box = layout.box()
        box.prop(self, "use_selection")
        box.prop(self, "use_visible")
        box.prop(self, "use_renderable")
        box.prop(self, "use_active_collection")
        box.prop(self, "use_active_scene")
        box.prop(self, "export_apply")

        box = layout.box()
        self.divine_settings.draw(context, box)

            
    @property
    def check_extension(self):
        return True
    
    def check(self, context):
        if self.log_message != "":
            print(self.log_message)
            helpers.report("{}".format(self.log_message), "WARNING")
            self.log_message = ""

        return False
        

    def invoke(self, context, event):
        scene_props = bpy.context.scene.ls_properties
        if scene_props.game != "unset":
            self.divine_settings.game = scene_props.game

        context.window_manager.fileselect_add(self)
        self.initialized = True

        return {'RUNNING_MODAL'}

    def cancel(self, context):
        pass


    def execute(self, context):
        try:
            helpers.current_operator = self
            return self.really_execute(context)
        finally:
            helpers.current_operator = None


    def really_execute(self, context):
        output_path = Path(self.properties.filepath)
        temp = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
        temp.close()
        gltf_path = Path(temp.name)

        context.scene.ls_properties.metadata_version = collada.ColladaMetadataLoader.LSLIB_METADATA_VERSION

        result = bpy.ops.export_scene.gltf(filepath=str(gltf_path), export_format='GLB', export_tangents=True,
                                  export_optimize_animation_keep_anim_object=True,
                                  export_bake_animation=True, 
                                  export_materials='NONE',
                                  export_morph=False, export_morph_animation=False,
                                  use_selection=self.use_selection, use_visible=self.use_visible,
                                  use_renderable=self.use_renderable, use_active_collection=self.use_active_collection,
                                  use_active_scene=self.use_active_scene, export_apply=self.export_apply)

        if result != {"FINISHED"}:
            return result

        addon_prefs = get_prefs(context)
        invoker = divine.DivineInvoker(addon_prefs, self.divine_settings)
        if not invoker.export_gr2(str(gltf_path), str(output_path), "glb"):
            return {"CANCELLED"}
        gltf_path.unlink()

        helpers.report("Export completed successfully.", "INFO")
        return {"FINISHED"}



class DIVINITYEXPORTER_OT_import_gltf(Operator, ImportHelper):
    """Import Divinity/Baldur's Gate models (glTF/GR2)"""
    bl_idname = "import_scene.dos2de_gltf"
    bl_label = "Import glTF/GR2"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext: StringProperty(
        name="File Extension",
        options={"HIDDEN"},
        default=".gr2"
    )

    filter_glob: StringProperty(default="*.gr2", options={"HIDDEN"})

    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty()

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

            addon_prefs = get_prefs(context)
            invoker = divine.DivineInvoker(addon_prefs, None)
            temp = tempfile.NamedTemporaryFile(suffix=".glb", delete=False)
            temp.close()
            gltf_path = Path(temp.name)
            if not invoker.import_gr2(str(input_path), str(gltf_path), "glb"):
                return {'CANCELLED'}

            bpy.ops.import_scene.gltf(filepath=str(gltf_path))

            gltf_path.unlink()            
            helpers.report("Import completed successfully.", "INFO")

        return {'FINISHED'}


classes = (
    DIVINITYEXPORTER_OT_export_gltf,
    DIVINITYEXPORTER_OT_import_gltf
)

def register():
    for cls in classes:
        register_class(cls)


def unregister():
    for cls in classes:
        unregister_class(cls)
