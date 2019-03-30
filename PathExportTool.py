# References:
#   Get global coordinate after constraints:    https://blenderartists.org/forum/archive/index.php/t-180777.html
#                                               https://blender.stackexchange.com/questions/7576/how-can-i-use-a-python-script-to-get-the-transformation-of-an-object
#   Custom properties:                          https://blenderartists.org/forum/archive/index.php/t-336028.html
#   OSC library:                                https://github.com/sergeLabo/blenderOSC
#   Raycast:                                    https://blender.stackexchange.com/questions/50716/strange-object-ray-cast-behavior 



# Function:

#   1: Iterate over group and collect all the light path curves

#   2: Create empty to be used for travseral across curves. Give it a Follow Path constraint with use_fixed_location = True

#   3: Iterate between specified start and end frames. For each frame:

#       1: Iterate over collected light path curves. For each curve:

#           1: Record the color of the curve

#           2: Set the empty Follow Path constraint target to the curve. Set the offset to 0.000.

#           3: Repeat until the offset >= 1:

#               1: Record the global position of the empty.

#               5: Increment the offset by a specificed Path Increment parameter until the empty has traveled a magnitude of at least the value of a specified Path Traversal Threshold (mm) parameter.

#       2: Send path color/coordinate information to Processing through OSC

#       3: Yield until receiving frame capture complete signal from processing. During this time, the following occurs outside of Blender:

#           1: Processing relays path information to Arduino.

#           2: When ready to execute, Arduino triggers Dragonframe to start the frame capture through the SWITCH trigger on DMC16

#           3: Arduino executes the light paths

#           4: Arduino waits until Dragonframe has completed capturing the frame, listening through the RELAY trigger on DMC16

#           5: Arduino sends message to processing that the frame is completed. Processing relays this to Blender, which advances to the next frame.

#        
#
# Features:

#   - Execute cancel

#   - Physical positions:
#       - Light painting machine origin position offset relative to Blender origin

#   - Do not attempt to draw light path points if they are outside of bounds of the machine
#       - Input for light painting bounds

#   - Set color to 0,0,0 to disable path.

#   - Path draw order optimization for time, pick closest next endpoint. Can do this once at initial collection.

#   - Specifiy start and end frame
#       - Values default to 0 - last frame


# Notes:
#   Ensure DMC16 is set to close relay -during- exposure.
#   Ensure ip_out matches IP reported in processing output on program startup
#   Ensure all power up, bash light, and settling times in dragonframe lighting settings are 0 seconds
#   Ensure frame move speed is 1x jog speed for slow axes of movement.
#   OSC from Processing to Blender will only work the first time this code is run. If the addon is reloaded, you will have to restart Blender for this direction of communication to work.
#   LED seems best shot around 4200K white balance

import bpy
import bmesh
import math
from bpy.types import Panel, Operator
from mathutils import Vector
from send_receive import Receive, Send

bl_info = {
    "name": "Light Painting Path Export Tool",
    "author": "Josh Sheldon",
    "category": "Import-Export",
    "blender": (2, 7, 9)    
}

ip_in = "127.0.0.1"
ip_out = "YOUR IP" # **YOUR IP ADDRESS**  Not sure how to change this on Processing side to just be localhost. Need to update this value to whatever processing says the address is
port_in = 9000
port_out = 8000
buffer_size = 1024

my_receiver = Receive(ip_in, port_in, buffer_size, verbose=True)
my_sender = Send(verbose=True)

props = None

executingPainting = False
isFirstMove = False
cancelClicked = False

currentColor = [0, 0, 0]
currentWorldPos = Vector([0, 0, 0])
currentMachinePos = Vector([0, 0, 0])

pathFollower = None
followPathConstraint = None

class ExecutePainting(Operator):
    global pathFollower
    
    bl_idname = 'lightpainting.executepainting'
    bl_label = 'Execute light painting animation'
    
    lightPaths = []
    lightPathDirections = []
 
    movingToNextPath = False
    outOfBounds = False
    overrideColor = False
    
    machineOffset = None
    machineStepsPerUnit = None
    machineSpeed = None
    machineBounds = None
    
    def pointInWorkspace(self, p):
        p = Vector([p.x, p.y, p.z]) - self.machineOffset # convert to machine space
        result = p.x >= 0 and p.y >= 0 and p.z >= 0 and p.x <= self.machineBounds.x and p.y <= self.machineBounds.y and p.z <= self.machineBounds.z
        #print("Checking point ", p, " bounds: ", self.machineBounds, result)
        return result
    
    def getPathPosition(self, path, alpha):
        global pathFollower, followPathConstraint
        
        pathStart = path.data.bevel_factor_start
        pathEnd = path.data.bevel_factor_end
        if (pathEnd < pathStart):
            pathStart, pathEnd = pathEnd, pathStart

        followPathConstraint.target = path
        followPathConstraint.offset_factor = (pathEnd - pathStart) * alpha + pathStart #max(min(alpha, pathEnd), pathStart)
        bpy.context.scene.update()
        
        pos = pathFollower.matrix_world.to_translation()
        return Vector([pos.x, pos.y, pos.z, 1])
    
    def getPathColor(self, path):
        color = None 
        isBlack = True 
        for node in path.material_slots[0].material.node_tree.nodes:
            if (node.bl_idname == "ShaderNodeEmission"):
                color = node.inputs[0].default_value
                isBlack = color[0] <= 0 and color[1] <= 0 and color[2] <= 0 
        return color, isBlack
    
    # Collect light paths, in optimized order for movement speed
    def collectPaths(self, context):
        global props
        followBlackPaths = props.follow_black_paths
        traverseThreshold = props.light_path_traverse_threshold
        
        self.lightPaths = []            # Path objects
        self.lightPathDirections = []   # 0 or 1 direction of path traversal
        
        lightPathsUnsorted = list(bpy.data.groups.get('LightPathGroup').objects)
        orderedLightPaths = []
        orderedLightPathDirections = []
        
        # Filter out all light paths not in the workspace or that are black or that are too short
        print("FILTERING OUT OF BOUNDS + BLACK + SHORT PATHS")
        for path in reversed(lightPathsUnsorted):
            start = self.getPathPosition(path, 0)
            end = self.getPathPosition(path, 1)
            mid = self.getPathPosition(path, 0.5)
            color, isBlack = self.getPathColor(path)
            
            if color is None:
                print("PATH ", path, " HAS NO EMISSION NODE TO DETERMINE COLOR")
                
            if (not self.pointInWorkspace(start) and not self.pointInWorkspace(end)):
                lightPathsUnsorted.remove(path)
                print("Filtered out of bounds path ", path)
            elif (isBlack and not followBlackPaths or color is None):
                lightPathsUnsorted.remove(path)
                print("Filtered black path ", path)
            elif (start - end).length < 0.0001 and (start - mid).length < 0.0001:
                lightPathsUnsorted.remove(path)
                print("Filtered short path ", path)
            
            
        # Determine first light path point by max height
        print("DETERMINING START POSITION")
        firstEndpointPosition = None
        firstPathIndex = 0
        firstPathDirection = 0
        
        for index, path in enumerate(lightPathsUnsorted):
            for direction in [0, 1]:
                pos = self.getPathPosition(path, direction)
                if (firstEndpointPosition is None or pos.z > firstEndpointPosition.z):
                    firstEndpointPosition = pos
                    firstPathIndex = index
                    firstPathDirection = direction
             
        if len(lightPathsUnsorted) > 0:           
            orderedLightPaths = [lightPathsUnsorted.pop(firstPathIndex)]
            orderedLightPathDirections = [firstPathDirection]
        
        # Get sorted list of light paths/directions in order of closest path to the last path's end point
        print("GETTING SORTED LIST OF LIGHT PATHS")
        for n in range(len(lightPathsUnsorted)):
            lastPath = orderedLightPaths[-1]
            lastPos = self.getPathPosition(lastPath, 1 - orderedLightPathDirections[-1])
    
            closestPathIndex = None
            pathDirection = None
            closestDist = None
            
            for index, path in enumerate(lightPathsUnsorted):
                for direction in [0, 1]:
                    pos = self.getPathPosition(path, direction)
                    distToLast = (pos - lastPos).length
                    if (closestPathIndex == None or distToLast < closestDist):
                        closestPathIndex = index
                        pathDirection = direction
                        closestDist = distToLast
                        
            orderedLightPaths.append(lightPathsUnsorted.pop(closestPathIndex))
            orderedLightPathDirections.append(pathDirection)
            
        self.lightPaths = orderedLightPaths
        self.lightPathDirections = orderedLightPathDirections
        
        print("Ordered light paths: ", self.lightPaths)
        print("Light path directions: ", self.lightPathDirections)
        
    def writePosition(self, pos):
        x, y, z = int(pos.x * self.machineStepsPerUnit.x), int(pos.y * self.machineStepsPerUnit.y), int(pos.z * self.machineStepsPerUnit.z)
        my_sender.simple_send_to("/blender/x", ['mov', x, y, z], (ip_out, port_out))
    
    def writeMovement(self, pos, doWriteNextPath):
        global currentMachinePos, currentWorldPos, currentColor, isFirstMove
        
        worldPos = pos
        machinePos = pos - self.machineOffset
        
        if (not self.pointInWorkspace(worldPos)):
            if (not self.outOfBounds):
                print("PATH LEFT MACHINE BOUNDS")
                self.outOfBounds = True
                self.setColorOverride(True)
                
            return False
        else:
            propInTheWay = False
            
            # iterate through scene props group and raycast for collisions
            props = list(bpy.data.groups.get('SceneProps').objects)
            for index, prop in enumerate(props):
                origin = prop.matrix_world.inverted() * currentWorldPos
                dest = prop.matrix_world.inverted() * worldPos
                direction = (dest - origin).normalized()
                distance = (dest - origin).length 
                hit, loc, norm, face = prop.ray_cast(origin, direction, distance)
            
                if (hit):
                    propInTheWay = True
                    break
            
            if propInTheWay:
                print("PROP IN THE WAY! ", self.movingToNextPath)
            
            # If first move or there is prop in the way and moving to a new path then avoid obstacle
            if (self.movingToNextPath and propInTheWay or isFirstMove):
                print("Something is in the way! Avoiding obstacle.")
                zHeight = max(min(self.propHeightLimit, self.machineBounds.z), 0)
                #if (self.machineAxisInversions[2]):
                #    zHeight = self.machineBounds.z
                #else:
                #    zHeight = 0
                    
                self.writePosition(Vector([currentMachinePos.x, currentMachinePos.y, zHeight]))
                self.writePosition(Vector([machinePos.x, machinePos.y, zHeight]))
                isFirstMove = False
                
            if doWriteNextPath:
                # NextPath signals are checkpoints at tge start of each path that
                # arduino uses to know when to break up light paths across the multiple exposures
                self.writeNextPath()
                self.writeColor(currentColor[0], currentColor[1], currentColor[2])
                   
            self.writePosition(machinePos)
            currentWorldPos = worldPos
            currentMachinePos = machinePos
            
            if (self.outOfBounds):
                self.outOfBounds = False
                self.setColorOverride(False)
                
            return True
            
            
    def writeColor(self, r, g , b):
        global currentColor
        r = int(r)
        g = int(g)
        b = int(b)
        currentColor = [r, g, b]
        if (not self.overrideColor):
            my_sender.simple_send_to("/blender/x", ['col', r, g, b], (ip_out, port_out))
        
    def setColorOverride(self, override):
        global currentColor
        self.overrideColor = override
        if (override):
            my_sender.simple_send_to("/blender/x", ['col', 0, 0, 0], (ip_out, port_out))
        else:
            self.writeColor(currentColor[0], currentColor[1] , currentColor[2])
      
    def writeSpeed(self):
        # steps per second
        sx, sy, sz = int(self.machineSpeed * self.machineStepsPerUnit.x), int(self.machineSpeed * self.machineStepsPerUnit.y), int(self.machineSpeed * self.machineStepsPerUnit.z)
        my_sender.simple_send_to("/blender/x", ['spd', sx, sy, sz], (ip_out, port_out))
        
    def writeWorkspaceSize(self):
        # steps
        wx, wy, wz = int(self.machineBounds.x * self.machineStepsPerUnit.x), int(self.machineBounds.y * self.machineStepsPerUnit.y), int(self.machineBounds.z * self.machineStepsPerUnit.z)
        my_sender.simple_send_to("/blender/x", ['siz', wx, wy, wz], (ip_out, port_out))
          
    def writeAxisInversion(self):
        a = self.machineAxisInversions
        my_sender.simple_send_to("/blender/x", ['inv', -1 if a[0] else 1, -1 if a[1] else 1, -1 if a[2] else 1], (ip_out, port_out))
        
    def writeLedCalibration(self):
        calR, calG, calB = int(self.ledCalibration[0] * 1000), int(self.ledCalibration[1] * 1000), int(self.ledCalibration[2] * 1000)
        my_sender.simple_send_to("/blender/x", ['cal', calR, calG, calB], (ip_out, port_out))
      
    def writeFrameNumber(self, context):
        my_sender.simple_send_to("/blender/x", ['frm', context.scene.frame_current], (ip_out, port_out))
        
    def writeNextPath(self):
        my_sender.simple_send_to("/blender/x", ['nxt', 0, 0, 0], (ip_out, port_out))
        
    def writeExposureCount(self):
        my_sender.simple_send_to("/blender/x", ['exc', self.exposureCount, 0, 0], (ip_out, port_out))
        
    def writeExposureTime(self):
        my_sender.simple_send_to("/blender/x", ['ext', self.exposureTime, 0, 0], (ip_out, port_out))
        
    def writeYieldThreshold(self):
        my_sender.simple_send_to("/blender/x", ['yel', math.floor(self.exposureYieldThreshold) * 1000, 0, 0], (ip_out, port_out))
         
    def writeFinish(self):
        my_sender.simple_send_to("/blender/x", ['fin'], (ip_out, port_out))
        
    
    # Send path info commands to machine
    def sendFrameMovement(self, context):
        global props, currentMachinePos, currentWorldPos, currentColor, pathFollower, followPathConstraint, isFirstMove
        
        print("Sending frame ", context.scene.frame_current)
        
        self.writeFrameNumber(context)
        self.writeWorkspaceSize()
        self.writeAxisInversion()
        self.writeSpeed()
        self.writeLedCalibration()
        self.writeExposureCount()
        self.writeExposureTime()
        self.writeYieldThreshold()
        
        # enable all layers so that geometry loads for collision avoidance raycasting
        enabledLayers = []
        for i in range(len(bpy.context.scene.layers)):
            if bpy.context.scene.layers[i] == False:
                enabledLayers.append(i)
                bpy.context.scene.layers[i] = True 
            
        # Collect ordered list of light paths
        self.collectPaths(context)

        # Iterate through ordered list and send commands
        isFirstMove = True
        lastPos = None        
        traverseIncrement = props.light_path_traverse_increment
        traverseThreshold = props.light_path_traverse_threshold
        
        for path, direction in zip(self.lightPaths, self.lightPathDirections):
            pathStart = path.data.bevel_factor_start
            pathEnd = path.data.bevel_factor_end
            if (pathEnd < pathStart):
                pathStart, pathEnd = pathEnd, pathStart
            
            followPathConstraint.target = path
            followPathConstraint.offset_factor = max(min(direction, pathEnd), pathStart)
            context.scene.update()
            pos = pathFollower.matrix_world.to_translation()
            lastPos = pos#.copy()
            
            self.writeColor(0,0,0)
            self.movingToNextPath = True
            self.writeMovement(pos, False)
            self.movingToNextPath = False
            
            color, isBlack = self.getPathColor(path)
            recordNextPathMarker = not isBlack
            currentColor = [color[0] * 255, color[1] * 255, color[2] * 255]
            
            alpha = 0.0
            while alpha <= 1.0:
                #print("Pos: "+ str(pos) + " Lastpos: " + str(lastPos) + " Dist: " + str((pos - lastPos).length))
                if (pos - lastPos).length >= traverseThreshold:
                    if self.writeMovement(pos, recordNextPathMarker) and recordNextPathMarker:
                        recordNextPathMarker = False
                    lastPos = pos

                alpha = alpha + traverseIncrement
                offset = abs(direction - alpha)
                offset = max(min(offset, pathEnd), pathStart)
                
                followPathConstraint.offset_factor = offset
                context.scene.update()
                pos = pathFollower.matrix_world.to_translation()

            self.writeMovement(pos, recordNextPathMarker)
        
        if self.homeWandAfterFrame:
            self.writeColor(0, 0, 0)
            zHeight = max(min(self.propHeightLimit, self.machineBounds.z), 0)
            self.writePosition(Vector([currentMachinePos.x, currentMachinePos.y, zHeight]))
            self.writePosition(Vector([0, 0, zHeight]))
        
        self.writeFinish()
        
        if context.scene.frame_current < context.scene.frame_end:
            bpy.ops.screen.frame_offset(delta = 1)
        
        # disable enabled layers
        for _, i in enumerate(enabledLayers):
            bpy.context.scene.layers[i] = False
    
    
    # Clean up objects and variables on finish/cancel
    def cleanup(self):
        global executingPainting, pathFollower
        executingPainting = False
        if not (pathFollower is None):
            bpy.context.scene.objects.active = pathFollower
            bpy.ops.object.delete()
            pathFollower = None
    
    
    # Modal is called during execution
    def modal(self, context, event):
        global cancelClicked, executingPainting
        
        if cancelClicked:
            self.cleanup()
            return {'CANCELLED'}
        
        if event.type == 'TIMER':
            # Check for incoming signal from OSC that path has been drawn
            data = my_receiver.get_data()
            if data:
                print("OSC data received: ", data)
            if not (data is None) and data[0] == "finished" and data[2] == context.scene.frame_current - 1:
                isLastFrame = context.scene.frame_current >= context.scene.frame_end
                self.sendFrameMovement(context)
                if isLastFrame:
                    self.cleanup()
                    return {'FINISHED'}
        
        return {'PASS_THROUGH'}


    # Execute is called once starting drawing
    def execute(self, context):          
        global props, cancelClicked, executingPainting, pathFollower, followPathConstraint
        
        executingPainting = True
        cancelClicked = False
        
        self.machineOffset = Vector(props.painting_robot_position)
        self.machineStepsPerUnit = Vector(props.painting_robot_steps_per_unit)
        self.machineSpeed = props.light_paint_max_speed
        self.machineBounds = Vector(props.painting_robot_bounds)
        self.machineAxisInversions = props.painting_robot_axis_inversions
        self.propHeightLimit = props.prop_height_limit
        self.ledCalibration = props.led_calibration
        self.exposureCount = props.num_exposures_per_frame
        self.exposureTime = props.exposure_time
        self.exposureYieldThreshold = props.exposure_yield_threshold
        self.homeWandAfterFrame = props.home_wand_after_frame
        
        bpy.ops.screen.animation_cancel(restore_frame = False)
        bpy.ops.screen.frame_jump(end = False)
        bpy.context.scene.update()
        
        bpy.ops.object.empty_add(location = (0,0,0))
        bpy.ops.object.constraint_add(type='FOLLOW_PATH')
        pathFollower = bpy.context.scene.objects.active
        pathFollower.name = "Path Follower"
        followPathConstraint = pathFollower.constraints["Follow Path"]
        followPathConstraint.use_fixed_location = True
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(1.0, context.window)
        wm.modal_handler_add(self)
        
        self.sendFrameMovement(context)
      
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        self.cleanup()
        wm = context.window_manager
        wm.event_timer_remove(self._timer)
    
    

class CancelExecution(Operator):
    bl_idname = 'lightpainting.cancelexecutepainting'
    bl_label = 'Cancel light painting execution'
    
    def execute(self, context):
        global cancelClicked
        cancelClicked = True
    
    
        return {'FINISHED'}


#Class for the panel with input UI
class View3dPanel(Panel):
    bl_idname = "OBJECT_PT_light_paint_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = 'Light Painting Execution'
    bl_context = 'objectmode'
    bl_category = 'Light Painting'
    
    
    # Show machine volume
    def setMachineVolumeIndicator(self, context):
        global props
        machineOffset = Vector(props.painting_robot_position)
        machineBounds = Vector(props.painting_robot_bounds)
        inversions = props.painting_robot_axis_inversions

        machineVolumeEmpty = bpy.data.objects.get("MachineVolume")
        if machineVolumeEmpty is None:
            oldActive = bpy.context.scene.objects.active
            bpy.ops.object.empty_add(type='CUBE', view_align=False, layers=(True, True, True, True, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False))
            machineVolumeEmpty = bpy.context.scene.objects.active
            bpy.context.scene.objects.active = oldActive
            machineVolumeEmpty.name = "MachineVolume"
            
        machineVolumeEmpty.scale = machineBounds / 2
        machineVolumeEmpty.location = machineOffset + machineBounds / 2
        
        machineOriginEmpty = bpy.data.objects.get("MachineOrigin")
        if machineOriginEmpty is None:
            oldActive = bpy.context.scene.objects.active
            bpy.ops.object.empty_add(type='ARROWS', view_align=False, layers=(True, True, True, True, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False))
            machineOriginEmpty = bpy.context.scene.objects.active
            bpy.context.scene.objects.active = oldActive
            machineOriginEmpty.name = "MachineOrigin"
            
        machineOriginEmpty.scale = machineBounds / 6
        machineOriginEmpty.location = machineOffset #+ Vector([machineBounds.x if inversions[0] else 0, machineBounds.y if inversions[1] else 0, machineBounds.z if inversions[2] else 0])   
            
    # Custom parameters
    bpy.types.Scene.light_path_traverse_increment = bpy.props.FloatProperty(name="Path Traversal Increment", description = "The amount the path position will be incremented as it traverses along a path from 0 to 1. Use lower values for longer paths.", default = 0.01, min = 0.001, max = 1.0, soft_min = 0.0, soft_max = 0.5, step = 0.001, precision = 3)
    
    bpy.types.Scene.light_path_traverse_threshold = bpy.props.FloatProperty(name="Path Traversal Threshold", description = "The distance threshold from the last recorded point until a new path point is recorded.", default = 0.5, min = 0, max = 100.0, soft_min = 0.0, soft_max = 2.0, step = 0.01, precision = 3, unit = 'LENGTH')
    
    bpy.types.Scene.follow_black_paths = bpy.props.BoolProperty(name="Follow Black Paths", description = "Follow paths that have a color of 0, 0, 0, which could be used as manual obstacle avoidance.", default = False)
    
    bpy.types.Scene.painting_robot_position = bpy.props.FloatVectorProperty(name="Painter Position", description = "The position of the light painting robot position origin relative to the Blender origin.", default = (-45/2, -45/2, 0), step = 0.1, precision = 2, unit = 'LENGTH', update = setMachineVolumeIndicator)
    
    bpy.types.Scene.painting_robot_steps_per_unit = bpy.props.FloatVectorProperty(name="Painter Steps / Unit", description = "Number of steps per unit distance.", default = (400, 400, 400),  precision = 2)
    
    bpy.types.Scene.painting_robot_bounds = bpy.props.FloatVectorProperty(name="Painter Bounds", description = "Bounds of light painting robot. Points outside of this volume will not be sent.", default = (45, 45, 20),  precision = 1, unit = 'LENGTH', update = setMachineVolumeIndicator)
    
    bpy.types.Scene.painting_robot_axis_inversions = bpy.props.BoolVectorProperty(name="Invert Axes", description = "Invert direction of each axis", default = (False, False, True), update = setMachineVolumeIndicator)
    
    bpy.types.Scene.light_paint_max_speed = bpy.props.FloatProperty(name="Light Painting Speed", description = "Travel speed for light painting robot.", default = 10.0, min = 0.1, max = 1000.0, soft_min = 0.1, soft_max = 1000.0, step = 0.1, precision = 1, unit = 'VELOCITY')
    
    bpy.types.Scene.prop_height_limit = bpy.props.FloatProperty(name="Prop Height Limit", description = "Height to retract Z axis to during obstacle avoidance.", default = 20.0, soft_min = 0, soft_max = 1000.0, step = 0.1, precision = 1, unit = 'LENGTH')
    
    bpy.types.Scene.led_calibration = bpy.props.FloatVectorProperty(name="LED Calibration", description = "RGB scaling values to correct LED colors", default = (0.4, 1.0, 1.0), min = 0.0, max = 1.0, step = 0.001, precision = 3, unit = 'NONE')
    
    bpy.types.Scene.num_exposures_per_frame = bpy.props.IntProperty(name="Exposures Per Frame", description = "Number of exposures per frame. Set to match Dragonframe.", min = 1, max = 20, default = 1)
  
    bpy.types.Scene.exposure_time = bpy.props.IntProperty(name="Exposure Time", description = "Duration of each exposure in seconds. Round down if cannot reach exact value. Set to max Dragonframe.", min = 1, max = 60, default = 30)
    
    bpy.types.Scene.exposure_yield_threshold = bpy.props.FloatProperty(name="Next Exposure Yield Threshold", description = "If a path begins within this many seconds of the end the of exposure, yield and resume at the next exposure. Set this to be about the amount of time it takes to draw the longest path.", min = 0, max = 60, default = 0.8, soft_min = 0.5, soft_max = 10, precision = 1)
       
    bpy.types.Scene.home_wand_after_frame = bpy.props.BoolProperty(name="Home Wand After Frame", description = "Send the wand to the home position after the final exposure of each frame.", default = False)
     
    # Add UI elements here
    # draw method executed every time anything changes.
    def draw(self, context): 
        global props, executingPainting
  
        layout = self.layout
        scene = context.scene
        props = scene
        
        # Set of SceneProps group for obstacle avoidance
        if not ('SceneProps' in bpy.data.groups):
                bpy.data.groups.new(name = 'SceneProps')
            
        # Path paremeters
        layout.label(text="Path Interpretation", icon = 'OUTLINER_OB_CURVE')
        row = layout.row()
        row.prop(props, "light_path_traverse_increment")
        row = layout.row()
        row.prop(props, "light_path_traverse_threshold")
        row = layout.row()
        row.prop(props, "follow_black_paths")

        # Hardware parameters
        layout.separator()
        layout.label(text="Hardware Parameters", icon = 'SCRIPTWIN')
        split = layout.split()
        col = split.column()
        col.prop(props, "painting_robot_position")
        col = split.column()
        col.prop(props, "painting_robot_bounds")
        
        row = layout.row()
        row.prop(props, "light_paint_max_speed")
        row = layout.row()
        row.prop(props, "painting_robot_steps_per_unit")
        row = layout.row()
        row.prop(props, "painting_robot_axis_inversions")
        row = layout.row()
        row.prop(props, "prop_height_limit")
        row = layout.row()
        row.prop(props, "led_calibration")
        
        # Exposure paremeters
        layout.label(text="Exposure Settings", icon = 'CAMERA_DATA')
        row = layout.row()
        row.prop(props, "num_exposures_per_frame")
        row = layout.row()
        row.prop(props, "exposure_time")
        row = layout.row()
        row.prop(props, "exposure_yield_threshold")
        
        # Start/end frames
        layout.separator()
        layout.label(text="Light Painting Execution", icon = 'FILE_TICK')
        row = layout.row(align=True)
        row.prop(context.scene, "frame_start")
        row = layout.row(align=True)
        row.prop(context.scene, "frame_end")
        row = layout.row(align=True)
        row.prop(props, "home_wand_after_frame")
        
        
        # Execute / cancel
        row = layout.row()
        row.scale_y = 2.0
        if executingPainting == False:
            row.operator('lightpainting.executepainting', text = 'Execute', icon = 'PLAY')
        else:
            row.operator('lightpainting.cancelexecutepainting', text = 'Cancel', icon = 'CANCEL')
                 
# Register
def register():
    bpy.utils.register_class(View3dPanel)
    bpy.utils.register_class(ExecutePainting)
    bpy.utils.register_class(CancelExecution)
    
# Unregister
def unregister():
    bpy.utils.unregister_class(View3dPanel)
    bpy.utils.unregister_class(ExecutePainting)
    bpy.utils.unregister_class(CancelExecution)
    
    
# Needed to run script in Text Editor
if __name__ == '__main__':
    register()
