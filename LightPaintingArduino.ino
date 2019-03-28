// SD read/write
#include <SPI.h>
#include <SD.h>

// Stepper libraries
#include <AccelStepper.h>
#include <MultiStepper.h>


// User settings
double ledBrightnessTrim[3] =  {0.4, 1.0, 1.0}; // Brightness tuning for LED
int homeFrameFrequency = 20; // Rehome all axes after this many frames
int homeStepsPerSecond = 4000;
int bashLightFadeOutTime = 4500; // wait this long after initially triggering dragonframe to start the first exposure
int timeBetweenFrameExposures = 800; // wait this long after triggering dragonframe for the next exposure before continuing painting
int mocoWaitTime = 500; // wait this amount of time to allow moco to move if this time is not already soaked up by bash light fade and communication



// Command and parsing values
File commandSequenceLog;
boolean receivingData; 
int parsePosition;
String stringVal;
String command;
int val;
int commandValue[3];
char serialReceiveCommand[4];
char serialReceiveValues[25];

// Settings (these are set by the settings is Blender)
int stepsPerSecond[3] = {1000, 1000, 1000};
long workspaceSize[3] = {0, 0, 0};
int axisDirections[3] = {1, 1, -1};
int exposuresPerFrame = 1;
int exposureTime = 30000;
int yieldForNextThreshold = 800;

// States
long pos[3] = {0, 0, 0};
int color[3] = {0, 0, 0};
boolean lowerLimitState[3];
int framesSinceHome = 2000;
long exposureStartTime;
long executeStartTime;
boolean lightStarted = false;
boolean firstMoveDone = false;
int currentFrame = 0;
int currentFrameExposure = 0;
int numFramesCaptured = 0;

// Pins
int stepperStepPins[3] = {17, 15, 19};
int stepperDirPins[3] = {29, 27, 31};
int colorPins[3] = {5, 3, 7};
int lowerLimits[3] = {36, 34, 32};
int dragonframeActivate = 46;
int dragonframeFinished = 47;
int SD_CSPin = 53;

// Steppers
AccelStepper stepperX(AccelStepper::DRIVER, stepperStepPins[0], stepperDirPins[0]);
AccelStepper stepperY(AccelStepper::DRIVER, stepperStepPins[1], stepperDirPins[1]);
AccelStepper stepperZ(AccelStepper::DRIVER, stepperStepPins[2], stepperDirPins[2]);
MultiStepper steppers;
int homeSpeed = 4;


void setup() {
  Serial.begin(9600);
  Serial.println("Initializing");

  if (!SD.begin(SD_CSPin)) {
    Serial.println("SD Initialization failed");
    return;
  }
  

  for (int i = 0; i < 3; i ++)
  {
    pinMode(colorPins[i], OUTPUT);
    analogWrite(colorPins[i], 0);
    pinMode(lowerLimits[i], INPUT);
  }

  pinMode(dragonframeActivate, OUTPUT);
  pinMode(dragonframeFinished, INPUT_PULLUP);
  
  digitalWrite(dragonframeActivate, HIGH);

  stepperX.setMaxSpeed(stepsPerSecond[0]);
  stepperY.setMaxSpeed(stepsPerSecond[1]);
  stepperZ.setMaxSpeed(stepsPerSecond[2]);
  
  steppers.addStepper(stepperX);
  steppers.addStepper(stepperY);
  steppers.addStepper(stepperZ);

  colorTest();
}


void loop() {
  delay(10);
  receiveData();

  if (framesSinceHome >= homeFrameFrequency)
  {
    if (framesSinceHome == homeFrameFrequency) // if not initial home
    {
      // Avoid colliding with props by retracting and moving to home corner before rehoming, which starts with vertical probe down.
      setPosition(pos[0], pos[1], -workspaceSize[2]);
      setPosition(workspaceSize[0] * ((axisDirections[0] + 1) / 2), workspaceSize[1] * ((axisDirections[1] + 1) / 2), pos[2]);
    }
    homeSteppers();
  }
  
  executePainting();

  Serial.println("fin");
}


void receiveData() {
  if (SD.exists("commands.txt"))
  {
    SD.remove("commands.txt");
  }
  commandSequenceLog = SD.open("commands.txt", FILE_WRITE);
  if (!commandSequenceLog)
  {
    Serial.println("error opening commands.txt");
  }
  else
  {
    receivingData = true;
    Serial.println("Waiting to receive data");
    
    while (receivingData)
    {
       if (Serial.available()) 
       {
          memset(serialReceiveCommand, 0, sizeof(serialReceiveCommand));
          memset(serialReceiveValues, 0, sizeof(serialReceiveValues));
          
          Serial.readBytesUntil(',', serialReceiveCommand, 4);
          Serial.readBytesUntil('\n', serialReceiveValues, 25);

          /* Including these prints causes bugs.
          Serial.print("Recorded command: ");
          Serial.print(serialReceiveCommand);
          Serial.print(" ");
          Serial.println(serialReceiveValues);
          */
          
          command = String(serialReceiveCommand);
          stringVal = String(serialReceiveValues);
          
          int c0 = stringVal.indexOf(',');
          int c1 = stringVal.indexOf(',', c0 + 1);

          commandValue[0] = stringVal.substring(0, c0).toInt();
          commandValue[1] = stringVal.substring(c0 + 1, c1).toInt();
          commandValue[2] = stringVal.substring(c1 + 1).toInt();


          // some commands need to be interpretted before reading frame:
          
          
          if (command == "mov")
          {
            commandValue[0] *= axisDirections[0];
            commandValue[1] *= axisDirections[1];
            commandValue[2] *= axisDirections[2];
          }
          else if (command == "siz")
          {
            setWorkspaceSize(commandValue[0], commandValue[1], commandValue[2]);
          }
          else if (command == "spd")
          {
            setMoveSpeed(commandValue[0], commandValue[1], commandValue[2]);
          }
          else if (command == "inv")
          {
            setAxisDirections(commandValue[0], commandValue[1], commandValue[2]);
          }
          else if (command == "cal")
          {
            setLedCalibration(commandValue[0] / 1000.0, commandValue[1] / 1000.0, commandValue[2] / 1000.0);
          }
          else if (command == "frm")
          {
             setFrame(commandValue[0]);
          }
          else if (command == "yel")
          {
             setYieldForNextTime(commandValue[0]);
          }
          else if (command == "fin")
          {
            Serial.println("Finished receiving data");
            receivingData = false;
          }

          commandSequenceLog.print(serialReceiveCommand);
          commandSequenceLog.print(",");
          commandSequenceLog.print(commandValue[0]);
          commandSequenceLog.print(",");
          commandSequenceLog.print(commandValue[1]);
          commandSequenceLog.print(",");
          commandSequenceLog.println(commandValue[2]);
       }
    }
    commandSequenceLog.close();
    
    Serial.println("Data received");
    delay(500);
  }
}


void fireDragonframe()
{
  Serial.println("Firing Dragonframe.");
  digitalWrite(dragonframeActivate, LOW);
  delay(200);
  digitalWrite(dragonframeActivate, HIGH);
}

void waitForDragonframeEnd()
{
  int sig = LOW;
  while (sig == LOW)
  {
    sig = digitalRead(dragonframeFinished);
    Serial.print("Waiting for Dragonframe finish exposure ");
    Serial.println(currentFrameExposure + 1);
    delay(200);
  }
}

void waitForMoco()
{
  Serial.println("Waiting for moco move.");
  int elapsed = millis() - executeStartTime;
  if (elapsed < mocoWaitTime)
    delay(mocoWaitTime - elapsed);
}

void executePainting()
{
  Serial.println("Beginning execution.");

  executeStartTime = millis();
  exposureStartTime = -10000;
  lightStarted = false;
  currentFrameExposure = -1;
  firstMoveDone = false;
  
  commandSequenceLog = SD.open("commands.txt");
  if (commandSequenceLog)
  {
    
    while (readNextCommand())
    {
      
      /*
      Serial.print("Next command: ");
      Serial.print(command);
      Serial.print(": ");
      Serial.print(commandValue[0]);
      Serial.print(",");
      Serial.print(commandValue[1]);
      Serial.print(",");
      Serial.println(commandValue[2]);
      //*/

      if (!lightStarted && (command.equals("col") && (commandValue[0] > 0 || commandValue[1] > 0 || commandValue[2] > 0) 
                            || command.equals("mov") && (color[0] > 0 || color[1] > 0 || color[3] > 0)))
      {
        lightStarted = true;
        int startupTime = 0;
        
        if (currentFrameExposure == 0)
        {
          startupTime = bashLightFadeOutTime;
        }
        else if (currentFrameExposure > 0)
        {
          startupTime = timeBetweenFrameExposures;
        }
        
        int elapsed = millis() - exposureStartTime;
        if (elapsed < startupTime)
        {
          delay(startupTime - elapsed); // Shutter isn't open yet because bash light is fading out; yield until shutter opens.
        }
      }
      
       if (command.equals("mov"))
       {
          if (!firstMoveDone && framesSinceHome == 0) // just homed, need to do object avoidance
          {
            setPosition(pos[0], pos[1], -workspaceSize[2]);
            setPosition(commandValue[0], commandValue[1], pos[2]);
            firstMoveDone = true;
          }
          setPosition(commandValue[0], commandValue[1], commandValue[2]);
       }
       else if (command.equals("col"))
       {
          setColor(commandValue[0], commandValue[1], commandValue[2]);
       }
       else if (command.equals("nxt"))
       {
          nextPathReached();
       }
       else if (command.equals("spd"))
       {
          setMoveSpeed(commandValue[0], commandValue[1], commandValue[2]);
       }
       else if (command.equals("exc"))
       {
          setExposureCount(commandValue[0]);
       }
       else if (command.equals("ext"))
       {
          setExposureTime(commandValue[0]);
       }
       else if (command.equals("fin"))
       {
          Serial.println("Fin command reached.");
       }
    }
    commandSequenceLog.close();
  }
  else
  {
    Serial.println("error opening commands.txt");
  }

  setColor(0, 0, 0);
  framesSinceHome++;

  Serial.println("Execution complete.");
  
  if (millis() - exposureStartTime < 1000) // if we reach the end of the painitng nearly immediately after starting the frame
  {
    Serial.println("Short execution stalling...");
    delay(1000); // delay so that dragonframe gets a chance to close the shooting relay.
  }

  soakRemainingExposures();
  numFramesCaptured++;
}


void colorTest()
{
  Serial.println("Color test: red");
  for (int i = 255; i > 0; i--)
  {
    setColor(i, 0, 0);
    delay(4);
  }
  Serial.println("Color test: green");
  for (int i = 255; i > 0; i--)
  {
    setColor(0, i, 0);
    delay(4);
  }
  Serial.println("Color test: blue");
  for (int i = 255; i > 0; i--)
  {
    setColor(0, 0, i);
    delay(4);
  }
  setColor(0, 0, 0);
}


void setColor(int r, int g, int b)
{
  color[0] = r;
  color[1] = g;
  color[2] = b;
  for (int i = 0; i < 3; i++)
  {
    analogWrite(colorPins[i], color[i] * ledBrightnessTrim[i]);
  }
}


void setWorkspaceSize(long x, long y, long z)
{
  workspaceSize[0] = x;
  workspaceSize[1] = y;
  workspaceSize[2] = z;
}

void setAxisDirections(int x, int y, int z)
{
  axisDirections[0] = x;
  axisDirections[1] = y;
  axisDirections[2] = z;
}

void setPosition(long x, long y, long z)
{
  pos[0] = x;
  pos[1] = y;
  pos[2] = z;

  steppers.moveTo(pos);
  steppers.runSpeedToPosition(); // Blocks until all are in position
}

void setMoveSpeed(int x, int y, int z)
{
  stepsPerSecond[0] = x;
  stepsPerSecond[1] = y;
  stepsPerSecond[2] = z;
  stepperX.setMaxSpeed(stepsPerSecond[0]);
  stepperY.setMaxSpeed(stepsPerSecond[1]);
  stepperZ.setMaxSpeed(stepsPerSecond[2]);
}

void setLedCalibration(float r, float g, float b)
{
  ledBrightnessTrim[0] = r;
  ledBrightnessTrim[1] = g;
  ledBrightnessTrim[2] = b;
}

void setExposureCount(int count)
{
  exposuresPerFrame = count;
}

void setExposureTime(int t)
{
  exposureTime = t * 1000;
}

void setFrame(int f)
{
  currentFrame = f;
}

void setYieldForNextTime(int t)
{
  yieldForNextThreshold = t;
}

void nextPathReached()
{
  // if current time is within exposure time - threshold, let dragonframe move onto next frame.
  if (currentFrameExposure < exposuresPerFrame - 1 && millis() - exposureStartTime > exposureTime - yieldForNextThreshold)
  {
    waitForDragonframeEnd();
    delay(800);
    fireDragonframe();
    
    exposureStartTime = millis();
    lightStarted = false;
    currentFrameExposure++;

    if (currentFrameExposure == 0)
    {
      waitForMoco();
    }
    
    Serial.print("Executing ");
    Serial.print(currentFrame);
    Serial.print(".");
    Serial.println(currentFrameExposure + 1);
  }
}


void soakRemainingExposures()
{
  for (int i = currentFrameExposure; i < exposuresPerFrame  - 1; i++)
  {
    waitForDragonframeEnd();
    delay(800);
    fireDragonframe();
    exposureStartTime = millis();
    currentFrameExposure++;
    delay(1000);
  }
}

boolean readNextCommand(){
  command = "";
  stringVal = "";
  parsePosition = 0;
  commandValue[0] = 0;
  commandValue[1] = 0;
  commandValue[2] = 0;
  
  while (commandSequenceLog.available()) 
  {
    /*
    Serial.print("Parsing: '");
    Serial.print(command);
    Serial.print(":");
    Serial.print(parsePosition);
    Serial.print(":");
    Serial.println(stringVal);//*/
    
    byte in = commandSequenceLog.read();
    if (in == 44) // comma
    {
      if (parsePosition >= 1)
      {
        if (!stringValToInt())
        {
          return false;
        }
          
        commandValue[parsePosition - 1] = val;
        stringVal = "";
      }
      parsePosition = parsePosition + 1;
    }
    else if (in == 13 or in == 10) // new line
    {
      if (commandSequenceLog.peek() == 13 or commandSequenceLog.peek() == 10) // why are there two!
      {
        commandSequenceLog.read();
      }

      if (!stringValToInt())
      {
        return false;
      }

      if (parsePosition == 3)
      {
        commandValue[parsePosition - 1] = val;
        return true;
      }
      else
      {
        Serial.println("Error reading file: newline reached before parse position reached third value");
        return false;
      }
    }
    else // other byte
    {
      if (parsePosition > 0)
      {
        stringVal = stringVal + (char)in;
      }
      else
      {
        command = command + (char)in;
      }
    }
  }
  
  return false;
}


boolean stringValToInt()
{
  val = stringVal.toInt();
  if (val == 0 && !stringVal.equals("0")) // toInt failed
  {
    Serial.print("Error reading file: toInt failed for string: '");
    Serial.print(stringVal);
    Serial.println('\'');
    
    while (true)
      delay(100);

    return false;
  }
  return true;
}


void homeSteppers()
{
  Serial.print("Homing steppers; workspace size: ");
  Serial.print(workspaceSize[0]);
  Serial.print(", ");
  Serial.print(workspaceSize[1]);
  Serial.print(", ");
  Serial.println(workspaceSize[2]);

  stepperX.setCurrentPosition(0);
  stepperY.setCurrentPosition(0);
  stepperZ.setCurrentPosition(0);
  pos[0] = 0;
  pos[1] = 0;
  pos[2] = 0;

  int restoreStepSpeed[3] = {stepsPerSecond[0], stepsPerSecond[1], stepsPerSecond[2]};
  setMoveSpeed(homeStepsPerSecond, homeStepsPerSecond, homeStepsPerSecond);

  bringStepperToLimit(2);
  stepperZ.setCurrentPosition(0);
  pos[2] = 0;
  setPosition(pos[0], pos[1], -workspaceSize[2]);
  bringStepperToLimit(0);
  stepperX.setCurrentPosition(0);
  pos[0] = 0;
  bringStepperToLimit(1);
  stepperY.setCurrentPosition(0);
  pos[1] = 0;
  //delay(5000);

  setPosition(pos[0], -workspaceSize[1] * ((axisDirections[1] + 1) / 2), pos[2]);
  setPosition(-workspaceSize[0] * ((axisDirections[0] + 1) / 2), pos[1], pos[2]);
  setPosition(pos[0], pos[1], -workspaceSize[2] * ((axisDirections[2] + 1) / 2));

  stepperX.setCurrentPosition(0);
  stepperY.setCurrentPosition(0);
  stepperZ.setCurrentPosition(0);
  pos[0] = 0;
  pos[1] = 0;
  pos[2] = 0;

  framesSinceHome = 0;

  setMoveSpeed(restoreStepSpeed[0], restoreStepSpeed[1], restoreStepSpeed[3]);

  Serial.println("Homing done");
  delay(300);
}


void bringStepperToLimit(int i)
{
  int homed = 0;
  long desiredPos[3] = {pos[0], pos[1], pos[2]};
  
  while (homed < 2)
  {
    lowerLimitState[i] = digitalRead(lowerLimits[i]);
    if (homed == 0)
    {
      if (lowerLimitState[i] == HIGH)
      {
        homed = 1;
        desiredPos[i] += homeSpeed * 4;
      }
      else
        desiredPos[i] += homeSpeed;
    }
    else if (homed == 1)
    {
      if (lowerLimitState[i] == LOW)
        homed = 2;
      else
        desiredPos[i] += -homeSpeed / 4;
        delay(15);
    }
    setPosition(desiredPos[0], desiredPos[1], desiredPos[2]);
    delayMicroseconds(5);
  }
}
