from pymodbus.client.sync import ModbusSerialClient as ModbusClient
import time
PORT = '/dev/ttyACM0'
# PORT = 'COM4'
BAUDRATE = 9600
SLAVE_ID = 1

client = ModbusClient(
    method='rtu',
    port=PORT,
    baudrate=BAUDRATE,
    stopbits=1,
    bytesize=8,
    parity='E',  
    timeout=1
)
connection = client.connect()

print('checking',connection)

# === Digital Input Readers (DI1 to DI8) ===
# read_di1
def whitelight():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[0] if not rr.isError() else False
    except Exception as e:
        return False

# read_di2
def uvlight():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[1] if not rr.isError() else False
    except Exception as e:
        return False

# read_di3
def machinebreak():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[2] if not rr.isError() else False
    except Exception as e:
        return False

# read_di4
def greenlight():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[3] if not rr.isError() else False
    except Exception as e:
        return False

# read_di5
def yellowlight():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[4] if not rr.isError() else False
    except Exception as e:
        return False
    
# read_di6
def redlight():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[5] if not rr.isError() else False
    except Exception as e:
        return False

# read_di7
def empty():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[6] if not rr.isError() else False
    except Exception as e:
        return False

# read_di8
def empty():
    try:
        rr = client.read_discrete_inputs(0, 8, unit=SLAVE_ID)
        return rr.bits[7] if not rr.isError() else False
    except Exception as e:
        return False

# === Relay ON/OFF Functions for All 8 Channels ===

def turn_on_whitelight():
    try: 
        client.write_coil(0, True, unit=SLAVE_ID)
    except Exception as e:
        return False
    
def turn_off_whitelight(): 
    try:
        client.write_coil(0, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_uvlight(): 
    try:
        client.write_coil(1, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_uvlight(): 
    try:
        client.write_coil(1, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_machine(): 
    try:
        client.write_coil(2, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_machie(): 
    try:
        client.write_coil(2, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_greenlight(): 
    try:
        client.write_coil(3, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_greenlight(): 
    try:
        client.write_coil(3, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_yellowlight(): 
    try:
        client.write_coil(4, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_yellowlight(): 
    try:
        client.write_coil(4, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_redlight(): 
    try:
        client.write_coil(5, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_redlight(): 
    try:
        client.write_coil(5, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_empty(): 
    try:
        client.write_coil(6, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_empty(): 
    try:
        client.write_coil(6, False, unit=SLAVE_ID)
    except Exception as e:
        return False


def turn_on_empty(): 
    try:
        client.write_coil(7, True, unit=SLAVE_ID)
    except Exception as e:
        return False

def turn_off_empty(): 
    try:
        client.write_coil(7, False, unit=SLAVE_ID)
    except Exception as e:
        return False





# turn_on_whitelight()
# time.sleep(2)
# turn_off_greenlight()

# Click the Start Button
# DI1(Discrete Input)
    # if status ON turn on the channel 1 and 5 
    # else status OFF turn on the channel 4

# Defect Detected
    # channel 2 ON--> stop and alarem  --> red light and alarem
    # channel 3 ON--> brake stop the machine
    # channel 4 ON--> Idle State checking --> yellow light

# Reset button 
    # channel 2 OFF --> 
    # channel 3 OFF -->

# Again click the start push button for machine 
    # check the status DI1 and DI2 

# every time check the status DI1 and DI2(some doubt)


# data = read_di1()  #return True machine on false not on 

# data = read_di2()  #return True machine on false not on 

# print(data)

# DI1 --> Machine On signal
# DI2 --> Rotation Signal 
# channel 1  -- camera light
# channel 2  -- aleram with redlight
# channel 3 -- brake the machine 
# channel 4  -- yellow light
# channel 5  -- green light



turn_off_redlight()


