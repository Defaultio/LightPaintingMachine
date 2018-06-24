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

Run _VertexPathCreate.py_ and enter edit mode to view the light path creation tool panel.

![alt text](Screenshots/VertexPathTool1.png)

Click the button to enter the path creation state.

![alt text](Screenshots/VertexPathTool2.png)

Select a series of verticies on the mesh and a path object will be generated, following your sequence of verticies. Press finish or the enter key when you're done.

On the backend, this is automating the usually tedious process of creating empty objects attached to each vertex, creating a path that connects the verticies, and connecting the path to the empty objects using hook modifiers so that the path translates and deforms with the mesh.

**Using _PathExportTool.py_ to export commands**

sdfg

**How this all interfaces with Dragonframe**

sdfg

**Incorporating motion control**

Motion control (or moco) will let you add camera movements and prop movements into your animations. For more info, check out this Blender addon: https://github.com/Defaultio/BlenderMoco/
