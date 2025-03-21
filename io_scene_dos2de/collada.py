from . import helpers
import xml.etree.ElementTree as et
import bpy

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
            helpers.report("LSLib profile data not found in Collada export; make sure you're using LSLib v1.16 or later!", "ERROR")
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
            helpers.report("Collada file was exported with a too old LSLib version, important metadata might be missing! Please upgrade your LSLib!", "ERROR")

        if meta_version > self.LSLIB_METADATA_VERSION:
            helpers.report("The Blender exporter plugin is too old for this LSLib version, please upgrade your exporter plugin!", "ERROR")


    def find_anim_settings(self):
        for anim in self.root.findall(f"./{self.SCHEMA}library_animations/{self.SCHEMA}animation"):
            settings = anim.find(f"{self.SCHEMA}extra/{self.SCHEMA}technique[@profile='LSTools']")
            if settings is not None:
                return settings

        return None
    
    def load_mesh_profile(self, geom, settings):
        if geom.attrib['name'] not in bpy.data.objects:
            helpers.report("Couldnt load metadata on geometry '" + geom.attrib['name'] + "' (object not found)", "ERROR")
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
                    helpers.report("Unrecognized DivModelType in mesh profile: " + ele.text)
            elif tag == 'IsImpostor' and ele.text == '1':
                props.impostor = True
            elif tag == 'ExportOrder':
                props.export_order = int(ele.text) + 1
            elif tag == 'LOD':
                props.lod = int(ele.text)
            elif tag == 'LODDistance':
                props.lod_distance = float(ele.text)
            else:
                helpers.report("Unrecognized attribute in mesh profile: " + tag)
    
    def load_mesh_profiles(self):
        for geom in self.root.findall(f"./{self.SCHEMA}library_geometries/{self.SCHEMA}geometry"):
            settings = geom.find(f"{self.SCHEMA}mesh/{self.SCHEMA}extra/{self.SCHEMA}technique[@profile='LSTools']")
            if settings is not None:
                self.load_mesh_profile(geom, settings)
    
    def load_bone_profile(self, bone, settings):
        bones = [b for b in self.armature.data.bones if b.name == bone.attrib['name']] 
        if len(bones) == 0:
            helpers.report("Couldnt load metadata on bone '" + bone.attrib['name'] + "' (object not found)", "ERROR")
            return
        
        bone = bones[0]
        props = bone.ls_properties
        for ele in list(settings):
            _, _, tag = ele.tag.rpartition('}')
            if tag == 'BoneIndex':
                props.export_order = int(ele.text) + 1
            else:
                helpers.report("Unrecognized attribute in bone profile: " + tag)
    
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
