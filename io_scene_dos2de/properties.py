from bpy.types import PropertyGroup, Panel, Mesh, Armature, Bone, Scene
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty, IntProperty, PointerProperty
from bpy.utils import register_class, unregister_class

game_versions = (
    ("dos", "DOS", "Divinity: Original Sin"),
    ("dosee", "DOS: EE", "Divinity: Original Sin - Enhanced Edition"),
    ("dos2", "DOS 2", "Divinity: Original Sin 2"),
    ("dos2de", "DOS 2: DE", "Divinity: Original Sin 2 - Definitive Edition"),
    ("bg3", "BG 3", "Baldur's Gate 3"),
    ("unset", "Unset", "Unset")
)

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
    root_model_name: StringProperty(
        name="Root Model Name",
        description="Model name to use when exporting to GR2",
        default=""
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
        if context.active_bone is not None:
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
        layout.prop(props, "root_model_name")


classes = (
    LSMeshProperties,
    LSArmatureProperties,
    LSBoneProperties,
    LSSceneProperties,
    OBJECT_PT_LSPropertyPanel,
    BONE_PT_LSPropertyPanel,
    SCENE_PT_LSPropertyPanel
)

def register():
    for cls in classes:
        register_class(cls)

    Mesh.ls_properties = PointerProperty(type=LSMeshProperties)
    Armature.ls_properties = PointerProperty(type=LSArmatureProperties)
    Bone.ls_properties = PointerProperty(type=LSBoneProperties)
    Scene.ls_properties = PointerProperty(type=LSSceneProperties)


def unregister():
    for cls in classes:
        unregister_class(cls)

    del Scene.ls_properties
    del Bone.ls_properties
    del Armature.ls_properties
    del Mesh.ls_properties
