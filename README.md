# BG3/DOS2 Collada Exporter for Blender 3.6 and later

An addon for Blender that allows you to import and export glTF/DAE/GR2 files for Baldur's Gate 3 and Divinity: Original Sin 2.

_[Be sure to grab the LaughingLeader Helpers addon for layer support and additional export setup on individual objects.](https://github.com/LaughingLeader/laughingleader_blender_helpers)_

## Features:  
* Export to glTF/dae, or export to gr2 if the path to divine.exe is set.
* Automatically rotate the object for DOS2/BG3's Y-Up world (Blender is Z-Up).
* Use the layer name, active object name, or action name (animations) when exporting.
* Use built-in presets for quick exporting.
* Specify project paths to skip having to manually navigate to the correct folder when exporting.
* Specific Custom Properties on meshes are exported (Rigid, Cloth, MeshProxy). You can also globally flag your meshes with one of these flags.
* BG3-specific settings are imported/exported: LOD, LOD distance, Skeleton resource info, mesh flags (Spring, Occluder, ...)

## Installing

### Manual Method  
* Download this repository as a zip (using the green Clone or download button).
* Save the addon somewhere where you can find it again.
* Extract the zip.
* Copy the folder `io_scene_dos2de`. Make sure this is the folder with the scripts under it (`io_scene_dos2de\__init__.py` etc).
* Paste the `io_scene_dos2de` folder into your addons folder. Default path:
```
%APPDATA%\Blender Foundation\Blender\3.6\scripts\addons
```
* (Optional) Refer to Blender's guide for installing addons here: [Install from File](https://docs.blender.org/manual/en/latest/preferences/addons.html#header). It has a tip section for setting up a separate scripts/addons folder, outside of your appdata.

### Cloning  
* In Blender, navigate to File -> User Preferences -> File.
* The path for "Scripts" is where Blender will read new addon folders from. Add a path if it's blank.
* [Clone the repository](https://help.github.com/articles/cloning-a-repository/).
* Create a junction to the `io_scene_dos2de` inside your scripts/addons folder.
  * You can create a junction with this command line command:
```
mklink /j "C:\Path1\io_scene_dos2de" "C:\Path2\scripts\addons\io_scene_dos2de"
```
| Rename | Description |
| --- | ----------- |
| Path1 | This should be the path where you cloned the repo. We want to junction the io_scene_dos2de folder inside that contains all the py scripts.|
| Path2 | This is where your scripts/addons folder for Blender is. Either the AppData folder, or the custom scripts folder you set. We want to junction the io_scene_dos2de folder with the py scripts to this folder. |
  * Alternatively, this program allows junction/symlink creation via right clicking files/folders in a file explorer: [Link Shell Extension](http://schinagl.priv.at/nt/hardlinkshellext/linkshellextension.html#download)
    * With this program installed, right click the io_scene_dos2de folder and select "Pick Link Source", then go to scripts/addons, right click the background, and select Drop As... -> Junction.

### Activating the Addon  
* In Blender, navigate to Edit -> Preferences -> Add-ons
* Check the checkbox next to "DOS2/BG3 Collada Exporter".


### Troubleshooting
* I don't see the addon inside Blender.  
  Make sure the folder with the scripts (io_scene_dos2de/__init__.py, etc) is the folder inside scripts/addons. Blender won't read a nested folder. For example, if your folder is located like so: `scripts/addons/io_scene_dos2de/io_scene_dos2de`, Blender won't load the scripts or recognize the addon.
* Blender says `LSLib path was not set up in addon preferences. Cannot convert to GR2.` Make sure you've set the Divine Path in the preferences settings. If you haven't already, you'll need to install [Norbyte's Export Tool](https://github.com/Norbyte/lslib), which will contain divine.exe.

## Preferences Settings
![image](https://github.com/user-attachments/assets/05fb8e8d-e5bc-4456-a8f9-04cf51918e7a)

### Divine Path  
This is the path to divine.exe, bundled with any release of [Norbyte's Export Tool](https://github.com/Norbyte/lslib). If set, the addon can import/export the GR2 format, using divine.

### Convert to GR2 by Default  
If checked, "Convert to GR2" will automatically be checked when exporting. Requires divine.exe's path to be set.

### Default Preset  
If set, the addon will default to the selected preset when opening it up for the first time.

### Projects  
Project paths can be configured for quicker exporting. 

#### Project Folder  
The "root" folder your blend files will be under. This is a parent folder the addon will compare your blend file's path against.

#### Export Folder  
When the above folder is found in the blend's path, this folder will be the default root when exporting.

### Use Preset Type for Export Subfolder  
If checked and a project folder is detected, the current preset will automatically determine the subfolder. For instance, if you have a project folder set, and an export folder set to Public/Modname_UUID/Assets, then selecting the "Model" preset defaults the exported file to "Assets/Model".

## Credits
This is a heavily modified version of Godot Engine's "Better" Collada Exporter for Blender, located here: [https://github.com/godotengine/collada-exporter](https://github.com/godotengine/collada-exporter)

Special thanks to Norbyte for developing and maintaining [https://github.com/Norbyte/lslib](https://github.com/Norbyte/lslib), which is the sole reason we can even convert models to DOS2's format in the first place. 
