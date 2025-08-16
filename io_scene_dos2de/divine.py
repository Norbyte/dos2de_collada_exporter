from pathlib import Path
import subprocess
import bpy
from . import helpers

class DivineInvoker:
    def __init__(self, addon_prefs, divine_prefs):
        self.addon_prefs = addon_prefs
        self.divine_prefs = divine_prefs

    def check_lslib(self):
        if self.addon_prefs.lslib_path is None or self.addon_prefs.lslib_path == "":
            helpers.report("LSLib path was not set up in addon preferences. Cannot convert to GR2.", "ERROR")
            return False
            
        lslib_path = Path(self.addon_prefs.lslib_path)
        if not lslib_path.is_file():
            helpers.report("The LSLib path set in addon preferences is invalid. Cannot convert to GR2.", "ERROR")
            return False
        
        return True

    def build_export_options(self):
        export_str = ""
        # Possible args:
        #"export-normals;export-tangents;export-uvs;export-colors;deduplicate-vertices;
        # deduplicate-uvs;recalculate-normals;recalculate-tangents;recalculate-iwt;flip-uvs;
        # force-legacy-version;compact-tris;build-dummy-skeleton;apply-basis-transforms;conform"

        divine_args = {
            "ignore_uv_nan" : "ignore-uv-nan",
            "x_flip_meshes": "x-flip-meshes",
            "mirror_skeletons": "mirror-skeletons"
        }

        gr2_args = {
            "yup_conversion" : "apply-basis-transforms",
            #"conform" : "conform"
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

    def build_import_options(self):
        args = ""
        divine_args = {
            "x_flip_meshes": "x-flip-meshes",
            "mirror_skeletons": "mirror-skeletons"
        }

        for prop,arg in divine_args.items():
            val = getattr(self.divine_prefs, prop, False)
            if val == True:
                args += "-e " + arg + " "

        return args
    
    def invoke_lslib(self, args):
        print("[DOS2DE-Collada] Starting GR2 conversion using divine.exe.")
        print("[DOS2DE-Collada] Sending command: {}".format(args))

        try:
            process = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        except OSError as e:
            helpers.report("Failed to launch lslib: " + str(e), "ERROR")
            return False

        print("STDERR: ", process.stderr)
        print("STDOUT: ", process.stdout)

        err = process.stderr
        if (len(err)):
            err += '\n'
        err += '\n'.join(process.stdout.splitlines()[-1:])
        
        if process.returncode != 0 or process.stdout.startswith('[FATAL] '):
            if process.stdout.startswith('[FATAL] Value glb is not allowed'):
                error_message = "LSLib v1.20 or later is required for glTF support"
            else:
                error_message = "Failed to convert GR2 (see the message log for more details). " + err
            helpers.report(error_message, "ERROR")
            return False
        else:
            return True


    def export_gr2(self, collada_path, gr2_path, format):
        if not self.check_lslib():
            return False
        gr2_options_str = self.build_export_options()
        divine_exe = '"{}"'.format(self.addon_prefs.lslib_path)
        game_ver = bpy.context.scene.ls_properties.game
        process_args = "{} --loglevel all -g {} -s {} -d {} -i {} -o gr2 -a convert-model {}".format(
            divine_exe, game_ver, '"{}"'.format(collada_path), '"{}"'.format(gr2_path), format, gr2_options_str
        )

        return self.invoke_lslib(process_args)

    def import_gr2(self, gr2_path, collada_path, format):
        if not self.check_lslib():
            return False
        gr2_options_str = self.build_import_options()
        divine_exe = '"{}"'.format(self.addon_prefs.lslib_path)
        process_args = "{} --loglevel all -g bg3 -s {} -d {} -i gr2 -o {} -a convert-model -e flip-uvs {}".format(
            divine_exe, '"{}"'.format(gr2_path), '"{}"'.format(collada_path), format, gr2_options_str
        )
        
        return self.invoke_lslib(process_args)
