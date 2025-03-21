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

    def build_gr2_options(self):
        export_str = ""
        # Possible args:
        #"export-normals;export-tangents;export-uvs;export-colors;deduplicate-vertices;
        # deduplicate-uvs;recalculate-normals;recalculate-tangents;recalculate-iwt;flip-uvs;
        # force-legacy-version;compact-tris;build-dummy-skeleton;apply-basis-transforms;conform"

        divine_args = {
            "ignore_uv_nan" : "ignore-uv-nan"
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
            helpers.report(error_message, "ERROR")
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
            helpers.report(error_message, "ERROR")
            return False
        else:
            return True
