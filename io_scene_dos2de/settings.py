from bpy.types import PropertyGroup
from bpy.props import BoolProperty, EnumProperty, PointerProperty
from bpy.utils import register_class, unregister_class

from . import properties

gr2_extra_flags = (
    ("DISABLED", "Disabled", ""),
    ("MESHPROXY", "MeshProxy", "Flags the mesh as a meshproxy, used for displaying overlay effects on a weapon and AllSpark MeshEmiters"),
    ("CLOTH", "Cloth", "The mesh has vertex painting for use with Divinity's cloth system"),
    ("RIGID", "Rigid", "For meshes lacking an armature modifier. Typically used for weapons"),
    ("RIGIDCLOTH", "Rigid&Cloth", "For meshes lacking an armature modifier that also contain cloth physics. Typically used for weapons")
)


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
    ) # pyright: ignore[reportInvalidTypeForm]

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

    srgb_colors: BoolProperty(
        name="sRGB Colors",
        description="Import mesh color channels as sRGB instead of linear",
        default=False
    )

    def draw(self, context, obj):
        obj.label(text="GR2 Import Options")
        obj.prop(self, "x_flip_meshes")
        obj.prop(self, "mirror_skeletons")
        obj.prop(self, "srgb_colors")


classes = (
    GR2_ExportSettings,
    Divine_ExportSettings,
    Divine_ImportSettings
)

def register():
    for cls in classes:
        register_class(cls)


def unregister():
    for cls in classes:
        unregister_class(cls)
