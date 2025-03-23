from . import helpers

gltf_ext_name = "EXT_lslib_profile"
LSLIB_GLTF_METADATA_VERSION = 3

class glTF2ExportUserExtension:

    def __init__(self):
        # We need to wait until we create the gltf2UserExtension to import the gltf2 modules
        # Otherwise, it may fail because the gltf2 may not be loaded yet
        from io_scene_gltf2.io.com.gltf2_io_extensions import Extension
        self.Extension = Extension
        self.scene_ext = {}


    def gather_scene_hook(self, gltf2_scene, blender_scene, export_settings):
        if gltf2_scene.extensions is None:
            gltf2_scene.extensions = {}
        self.scene_ext["MetadataVersion"] = LSLIB_GLTF_METADATA_VERSION
        gltf2_scene.extensions[gltf_ext_name] = self.Extension(
            name = gltf_ext_name,
            extension = self.scene_ext,
            required = False
        )


    def gather_skin_hook(self, gltf2_skin, blender_object, export_settings):
        bone_order = {}
        for bone in blender_object.data.bones[:]:
            bone_order[bone.name] = bone.ls_properties.export_order - 1
        self.scene_ext["BoneOrder"] = bone_order


    def gather_mesh_hook(self, gltf2_mesh, blender_mesh, blender_object, vertex_groups, modifiers, materials, export_settings):
        ls_props = blender_mesh.ls_properties
        if gltf2_mesh.extensions is None:
            gltf2_mesh.extensions = {}
        gltf2_mesh.extensions[gltf_ext_name] = self.Extension(
            name = gltf_ext_name,
            extension = {
                "Rigid": ls_props.rigid,
                "Cloth": ls_props.cloth,
                "MeshProxy": ls_props.mesh_proxy,
                "ProxyGeometry": ls_props.proxy,
                "Spring": ls_props.spring,
                "Occluder": ls_props.occluder,
                "ClothPhysics": ls_props.cloth_physics,
                "Cloth01": ls_props.cloth_flag1,
                "Cloth02": ls_props.cloth_flag2,
                "Cloth04": ls_props.cloth_flag4,
                "Impostor": ls_props.impostor,
                "ExportOrder": ls_props.export_order,
                "LOD": ls_props.lod,
                "LODDistance": ls_props.lod_distance
            },
            required = False
        )


class glTF2ImportUserExtension:
    scene_ext = None
    armature = None

    def gather_import_scene_before_hook(self, gltf_scene, blender_scene, gltf):
        ls_props = blender_scene.ls_properties
        if gltf_scene.extensions is not None and gltf_ext_name in gltf_scene.extensions:
            ext = gltf_scene.extensions[gltf_ext_name]
            meta_version = ext['MetadataVersion']
            ls_props.metadata_version = meta_version
            self.scene_ext = ext
            if meta_version < LSLIB_GLTF_METADATA_VERSION:
                helpers.report("GLTF file was exported with a too old LSLib version, important metadata might be missing! Please upgrade your LSLib!", "ERROR")

            if meta_version > LSLIB_GLTF_METADATA_VERSION:
                helpers.report("The Blender exporter plugin is too old for this LSLib version, please upgrade your exporter plugin!", "ERROR")


    def gather_import_scene_after_nodes_hook(self, gltf_scene, blender_scene, gltf):
        if self.armature is not None and self.scene_ext is not None and 'BoneOrder' in self.scene_ext:
            bone_order = self.scene_ext['BoneOrder']
            for bone in self.armature.bones[:]:
                bone.ls_properties.export_order = bone_order[bone.name] + 1


    def gather_import_node_after_hook(self, vnode, gltf_node, blender_object, gltf):
        if blender_object.type == 'ARMATURE':
            self.armature = blender_object.data


    def gather_import_mesh_after_hook(self, gltf_mesh, blender_mesh, gltf):
        ls_props = blender_mesh.ls_properties
        if gltf_mesh.extensions is not None and gltf_ext_name in gltf_mesh.extensions:
            ext = gltf_mesh.extensions[gltf_ext_name]
            ls_props.rigid = ext['Rigid']
            ls_props.cloth = ext['Cloth']
            ls_props.mesh_proxy = ext['MeshProxy']
            ls_props.proxy = ext['ProxyGeometry']
            ls_props.spring = ext['Spring']
            ls_props.occluder = ext['Occluder']
            ls_props.cloth_physics = ext['ClothPhysics']
            ls_props.cloth_flag1 = ext['Cloth01']
            ls_props.cloth_flag2 = ext['Cloth02']
            ls_props.cloth_flag4 = ext['Cloth04']
            ls_props.impostor = ext['Impostor']
            ls_props.export_order = ext['ExportOrder']
            ls_props.lod = ext['LOD']
            ls_props.lod_distance = ext['LODDistance']
