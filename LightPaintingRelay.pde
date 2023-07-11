/*
 * Relay movement information from Blender to Arduino and frame complete notice from Arduino back to Blender
 */

int PORT_NUM = 0; //change the 0 to a 1 or 2 etc. to match Arduino port

import java.util.*;
import processing.serial.*;
import oscP5.*;
import netP5.*;
  
OscP5 oscP5;
NetAddress myRemoteLocation;

Serial myPort;

boolean executionFinished = false;
int currentFrame = -1;
String currentState = "";
String arduinoSerial = "";
PFont font;


List<String> commandList = new ArrayList<String>();
List<int[]> valueList = new ArrayList<int[]>();

void setup()
{
  size(600,600);
  font = createFont("Courier New",16,true); 
  
  frameRate(25);

  /* This did not properly receive for some reason:
  OscProperties myProperties = new OscProperties();
  myProperties.setDatagramSize(10000); 
  myProperties.setRemoteAddress(new NetAddress("10.0.0.2", 8000));
  oscP5 = new OscP5(this, myProperties);
  */

  oscP5 = new OscP5(this, 8000);
  myRemoteLocation = new NetAddress("127.0.0.1", 9000);
  
  printArray(Serial.list());
  String portName = Serial.list()[PORT_NUM];
  myPort = new Serial(this, portName, 9600);
  myPort.bufferUntil('\n'); 
  
  currentState = "Waiting for OSC input from Blender";
  
  oscP5.send(new OscMessage("/startup"), myRemoteLocation); 
}


void draw()
{
  background(0); 
  textFont(font);
  fill(255);
  textAlign(CENTER, CENTER);
  text(currentState + "\n Arduino Serial: " + arduinoSerial, 0, 0, width, height); 

}


void relayToArduino()
{
  int numCommands = commandList.size();
  currentState = "Executing " + str(numCommands) + " commands";
  
  for (int i = 0; i < commandList.size(); i++)
  { 
    String command = commandList.get(i);
    int values[] = valueList.get(i);
    int a = values[0];
    int b = values[1];
    int c = values[2];
    
    String commandString = command+","+a+","+b+","+c+"\n";
    currentState = "Writing command " + str(i) + "/" + str(numCommands) + ": " + commandString;
    myPort.write(commandString); 
    
    delay(10);
  }
  
  currentState = "Waiting for Arduino finish. Current frame: " + str(currentFrame);
  
  executionFinished = false;
  
  while (!executionFinished)
  {
    delay(200);
  }
  
  paintingExecutionFinished();

  commandList = new ArrayList<String>();
  valueList = new ArrayList<int[]>();
}


void serialEvent(Serial port)
{
  String val = port.readStringUntil('\n');
  arduinoSerial = val;
  
  String command = val.substring(0, 3);
  if (command.equals("fin"))
  {
    executionFinished = true; 
  }
}



void paintingExecutionFinished()
{
  currentState = "Painting execution finished; returning OSC to blender";
  
  OscMessage myMessage = new OscMessage("/finished");
  myMessage.add(currentFrame); /* add an int to the osc message */

  /* send the message */
  oscP5.send(myMessage, myRemoteLocation); 
  
  currentState = "Sent OSC finished message to Blender:\n finished " + str(currentFrame);
}



/* incoming osc message are forwarded to the oscEvent method. */
void oscEvent(OscMessage theOscMessage)
{
  String command = theOscMessage.get(0).stringValue();
  commandList.add(command);
  
  //println("Received OSC command: ", command);
    
  if (command.equals("fin"))
  {
    valueList.add(new int[] {0, 0, 0});
    relayToArduino();
  }
  else if (command.equals("frm"))
  {
    currentFrame = theOscMessage.get(1).intValue(); 
    valueList.add(new int[] {currentFrame, 0, 0});
  }
  else
  {
    int a = theOscMessage.get(1).intValue();
    int b = theOscMessage.get(2).intValue();
    int c = theOscMessage.get(3).intValue();
    //println(a, " ", b, " ", c);
    valueList.add(new int[] {a, b, c});
  }
}
