# LightPaintingMachine

This is the Blender, Processing, and Arduino code that enable use of a CNC light painting machine to make pretty pictures and animations. A basic outline of how this works is as follows:

* Light paths are defined and animated in Blender. _VertexPathCreate.py_ is a Blender addon that makes adorning path objects to animated meshes easy.
* _PathExportTool.py_ is another Blender addon that iterates through each frame of animation and converts the light paths into a command sequence that can be followed by the Arduino
* The commands are sent through OSC and received by _LightPaintingRelay.pde_, a Processing sketch which relays the commands through serial to the Arduino.
* The serial commands are received by the Arduino, running _LightPaintingArduino.ino_. The Arduino executes the command sequence.
* When finished, the Arduino indicates it is finished by sending a serial command to Processing, which relays it back to Blender through OSC.
* When _PathExportTool.py_ in Blender receives the finished command, it sends the command sequence for the next exposure. This loop continues until all exposures are complete.

![alt text](Screenshots/ToolPanel.png)

**Using _VertexPathCreate.py_ to adorn light path objects to animated meshes**

dsfg

**Using _PathExportTool.py_ to export commands**

sdfg

**How this all interfaces with Dragonframe**

sdfg

**Incorporating motion control**

Motion control (or moco) will let you add camera movements and prop movements into your animations. For more info, check out this addon: https://github.com/Defaultio/BlenderMoco/
