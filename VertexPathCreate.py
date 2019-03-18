# Path drawing tool to draw light path curves on meshes and hook them to verticies
#
# Template from: https://www.youtube.com/watch?v=Ywza-zyAJzE
#

bl_info = {
    "name": "Adorn Mesh Vertices With Path Tool",
    "author": "Josh Sheldon",
    "category": "Add Curve",
    "blender": (2, 7, 9)    
}


import bpy
import bmesh
from bpy.types import Panel, Operator
from mathutils import Vector

finishClicked = False
cancelClicked = False
buildingPath = False
undoClicked = False


# Enter build path mode operator
class BuildPathOperator(Operator):
    bl_idname = 'lightpainting.buildlightpath'
    bl_label = 'Build light path'
    
    selectedMesh = None
    pathCurve = None
    vertexList = []
    emptyList = []
    
    
    # Enter object mode and store the selected mesh for later recall
    def objectMode(self):
        bpy.ops.object.mode_set(mode='OBJECT')
        self.selectedMesh = bpy.context.scene.objects.active
        
        
    # Reselect the original mesh and enter edit mode
    def editMode(self):
        bpy.context.scene.objects.active = self.selectedMesh
        bpy.ops.object.mode_set(mode='EDIT') 
    
    
    # Set up light circle to be used as path bevel object, path material, and light path group, if they doesn't already exist
    def initializeLightCircle(self):
        self.objectMode()
        if bpy.data.objects.get("LightCircle") is None:
            bpy.ops.curve.primitive_bezier_circle_add(location=(0, 0, -5), layers=(False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False))
            bpy.ops.transform.resize(value=(0.375, 0.375, 0.375))
            bpy.context.scene.objects.active.name = "LightCircle"
            
        if not ('LightPathMaterial' in bpy.data.materials):
            mat = bpy.data.materials.new(name = 'LightPathMaterial')
            mat.diffuse_color = (0.2, 1, 0.2)
        
        if not ('LightPathGroup' in bpy.data.groups):
            bpy.data.groups.new(name = 'LightPathGroup')
            
        self.editMode()
        
        
    # Refresh path curve
    def refreshPath(self):
        self.objectMode()
        
        if not (self.pathCurve is None):
            bpy.ops.object.select_all(action='DESELECT')
            self.pathCurve.select = True
            bpy.ops.object.delete() # this causes occasional crashes?
            self.pathCurve = None
            
        if len(self.vertexList) >= 2:
            curvedata = bpy.data.curves.new(name="LightPathNurbsCurve", type='CURVE')  
            curvedata.dimensions = '3D'  
          
            firstVertex = self.selectedMesh.data.vertices[self.vertexList[0]].co
            
            objectdata = bpy.data.objects.new("LightPath", curvedata)  
            objectdata.location = self.selectedMesh.matrix_world * firstVertex
            bpy.context.scene.objects.link(objectdata)  
          
            spline = curvedata.splines.new('NURBS')  
            spline.points.add(len(self.vertexList)-1)  
            
            for index, vertexIndex in enumerate(self.vertexList):
                empty = self.emptyList[index]
                x, y, z = self.selectedMesh.matrix_world * self.selectedMesh.data.vertices[vertexIndex].co - self.selectedMesh.matrix_world * firstVertex
                spline.points[index].co = (x, y, z, 1) # last parameter is weight
          
            spline.order_u = 3 #len(spline.points)-1
            spline.use_endpoint_u = True
            
            curvedata.use_fill_caps = True
            curvedata.bevel_object = bpy.data.objects["LightCircle"]
            objectdata.layers=(False, False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False)
            
            self.pathCurve = objectdata
            objectdata.data.materials.append(bpy.data.materials['LightPathMaterial'])
            
            bpy.data.groups.get('LightPathGroup').objects.link(objectdata)
            
        self.editMode()



    # Finish up the light path
    def finishBuildPath(self):
        #https://blender.stackexchange.com/questions/13484/using-python-to-create-a-curve-and-attach-its-endpoints-with-hooks-to-two-sphere
        bpy.ops.object.mode_set(mode='OBJECT')
        
        for index, vertexIndex in enumerate(self.vertexList):
            empty = self.emptyList[index]
            
            # create hook
            hookName = "Hook"+str(index)
            hook = self.pathCurve.modifiers.new(hookName, 'HOOK')
            hook.object = empty
            
            # vertex parent empty
            bpy.context.scene.objects.active = self.selectedMesh
            empty.select = True
            bpy.ops.object.parent_set(type='VERTEX') # this caused crashes occasionally in the vertex selected function
            bpy.ops.object.select_all(action='DESELECT')
            
        #self.pathCurve['light_path_transparency'] = bpy.props.FloatProperty(name="Path Transparency", description = "Transparency of light path, this value is multiuplied by the color for the final value. Can be used with animation to fade paths in or disable paths.", default = 0.0, min = 0.0, max = 1.0, soft_min = 0.0, soft_max = 1.0, step = 0.01, precision = 2)
        
        bpy.context.scene.objects.active = self.pathCurve
        bpy.ops.object.mode_set(mode='EDIT') 
        bpy.ops.curve.select_all(action='DESELECT')

        for index, vertexIndex in enumerate(self.vertexList):
            hookName = "Hook"+str(index)
            point = self.pathCurve.data.splines[0].points[index]
            
            point.select = True

            bpy.ops.object.hook_assign(modifier = hookName)
            bpy.ops.object.hook_reset(modifier = hookName)

            
            bpy.ops.curve.select_all(action='DESELECT') # simply using point.select = False did not work. Only the first point assigned correctly, the rest of the points had to be reassigned.
        
        
        bpy.ops.object.mode_set(mode='OBJECT')
        self.editMode()
        self.report({'INFO'}, 'Path created!')  
        
        
    # A vertex is selected, add a new empty at that point and parent it to the vertex
    def vertexSelected(self, vertex):
        index = vertex.index
        self.vertexList.append(index)
        
        self.objectMode()
        
        position = self.selectedMesh.data.vertices[index].co

        bpy.ops.object.empty_add(location=self.selectedMesh.matrix_world*position, layers=(False, True, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False, False))
        bpy.ops.transform.resize(value=(2, 2, 2))
        
        newEmpty = bpy.context.scene.objects.active
        self.emptyList.append(newEmpty)
        
        self.editMode()
        self.refreshPath()
        
        
    # Delete most recent vertex
    def undoPath(self):
        if len(self.emptyList) > 0:
            self.objectMode()
            
            self.emptyList[-1].select = True
            bpy.ops.object.delete()
            
            self.emptyList = self.emptyList[:-1]
            self.vertexList = self.vertexList[:-1]
            
            self.editMode()
            self.refreshPath()
            
            bpy.ops.mesh.select_all(action='DESELECT')
        else:
            cancelClicked = True
    
    
    # The path build was canceled, clean up everything we created
    def cancelCleanup(self):
        self.objectMode()
        bpy.ops.object.select_all(action='DESELECT')
        
        if not self.pathCurve is None:
            self.pathCurve.select = True
            
        for index, empty in zip(self.vertexList, self.emptyList):
            empty.select = True
            
        bpy.ops.object.delete()
        
        self.editMode()
        
        
    # The path build was finished or canceled, clean up some lists
    def pathDrawDone(self):
        del self.vertexList[:]
        del self.emptyList[:]
        del self.pathCurve
        
    
    # Modal is called while the path build is active
    def modal(self, context, event):
        global finishClicked, cancelClicked, undoClicked, buildingPath
        
        if not (bpy.context.object.mode == 'EDIT'):
            cancelClicked = True
        
        if event.type == 'ESC' and event.value == 'CLICK' or event.type == 'RIGHTMOUSE' or cancelClicked:
            buildingPath = False
            self.cancelCleanup()
            self.pathDrawDone()
            print("Canceled")
            return {'CANCELLED'}
            
        if finishClicked or event.type == 'LINE_FEED' and event.value == 'CLICK':
            buildingPath = False
            print("Finished\n" + str(self.vertexList))
            
            if len(self.vertexList) < 2:
                self.report({'WARNING'}, 'Not enough verticies selected to build path')
                self.cancelCleanup()
                self.pathDrawDone()
                return {'CANCELLED'}
            else:  
                self.finishBuildPath()
                self.pathDrawDone()
                return {'FINISHED'}
            
        if undoClicked or event.type == 'BACK_SPACE' and event.value == 'CLICK':
            undoClicked = False
            self.undoPath()
            print("UNDO")
        
        if event.type == 'LEFTMOUSE':  
            ob = bpy.context.object
            me = ob.data
            bm = bmesh.from_edit_mesh(me)
            if bm.select_history:
                elem = bm.select_history[-1]
                if isinstance(elem, bmesh.types.BMVert):
                    if not (len(self.vertexList) > 0 and self.vertexList[-1] == elem.index):
                        self.vertexSelected(elem)
                
        return {'PASS_THROUGH'}


    # Execute is called once when entering path build mode
    def execute(self, context):
        global finishClicked, cancelClicked, buildingPath
        finishClicked = False
        cancelClicked = False
        buildingPath = True
        self.pathCurve = None
        self.vertexList = []
        self.emptyList = []
        
        bpy.context.scene.layers[0] = True
        bpy.context.scene.layers[1] = True
        bpy.context.scene.layers[2] = True
        bpy.ops.screen.animation_cancel(restore_frame = False)
        bpy.ops.screen.frame_jump(end = False)
        self.initializeLightCircle()
        
        bpy.ops.mesh.select_all(action='DESELECT')
        
        wm = context.window_manager
        wm.modal_handler_add(self)
        
        return {'RUNNING_MODAL'}

    
    
class FinishPathOperator(Operator):
    bl_idname = 'lightpainting.finishlightpath'
    bl_label = 'Finish light path'
    bl_description = 'Finish light path (hotkey ENTER)'
    
    def execute(self, context):
        global finishClicked
        finishClicked = True
        
        return {'FINISHED'}
    
    
class CancelPathOperator(Operator):
    bl_idname = 'lightpainting.cancellightpath'
    bl_label = 'Cancel light path'
    bl_description = 'Cancel light path creation (hotkey ESCAPE)'
    
    def execute(self, context):
        global cancelClicked
        cancelClicked = True
        
        return {'FINISHED'}
    
class UndoPathOperator(Operator):
    bl_idname = 'lightpainting.undolightpath'
    bl_label = 'Undo'
    bl_description = 'Undo last vertex selection (hotkey BACKSPACE)'
    
    def execute(self, context):
        global undoClicked
        undoClicked = True
        
        return {'FINISHED'}


        

#Class for the panel with input UI
class View3dPanel(Panel):
    bl_idname = "PAINTING_PT_path_create"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'TOOLS'
    bl_label = 'Light Painting Tools'
    bl_context = 'mesh_edit'
    bl_category = 'Light Painting'

    # Add UI elements here
    # draw method executed every time anything changes.
    def draw(self, context): 
        global buildingPath
        layout = self.layout
        
        # Apply scale operator
        
        if buildingPath == False:
            row = layout.row()
            row.operator('lightpainting.buildlightpath', text = 'Path from verticies', icon = 'IPO_EXPO')
        else:
            col = layout.column()
            col.operator('lightpainting.finishlightpath', text = 'Finish', icon = 'FILE_TICK')
            col.separator()
            col.operator('lightpainting.undolightpath', text = 'Undo', icon = 'LOOP_BACK')
            col.separator()
            col.operator('lightpainting.cancellightpath', text = 'Cancel', icon = 'CANCEL')
        
        
        
    
# Register
def register():
    bpy.utils.register_class(View3dPanel)
    bpy.utils.register_class(BuildPathOperator)
    bpy.utils.register_class(FinishPathOperator)
    bpy.utils.register_class(CancelPathOperator)
    bpy.utils.register_class(UndoPathOperator)
    
# Unregister
def unregister():
    bpy.utils.unregister_class(View3dPanel)
    bpy.utils.unregister_class(BuildPathOperator)
    bpy.utils.unregister_class(FinishPathOperator)
    bpy.utils.unregister_class(CancelPathOperator)
    bpy.utils.unregister_class(UndoPathOperator)
    
    
# Needed to run script in Text Editor
if __name__ == '__main__':
    register()
