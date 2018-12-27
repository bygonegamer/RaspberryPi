import MySQLdb
import os
import RPi.GPIO as GPIO
import time
import sys
import datetime
import pickle

def get_temp_rh():
    gpiovals = [] 
    # Ask for response from DHT11:
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(4, GPIO.OUT)
    time.sleep(0.01)
    GPIO.output(4, GPIO.HIGH)
    time.sleep(0.02)
    GPIO.output(4, GPIO.LOW)
    time.sleep(0.015) #MCU start signal pulls low >18ms
    # setup for responce (20-40us) (pullup resistor 5kOhm does this)
    GPIO.setup(4, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    
    # We have to intrepret the input now beacuse there is no sync in transmission
    # I understand GPIO is ~1MHz read (1us). DHT11 process reads out ~4ms
    # Response begins w/ LOW 80us, HIGH 80us, LOW & begins transmission
    # Each BIT starts with 50us LOW, then LENGTH of following HIGH determins BIT value
    # 26-28us HIGH == 0
    # 70us HIGH    == 1
    # Readout Process:
    for i in xrange(3200):
        gpiovals.append(GPIO.input(4))
    GPIO.cleanup()

    # Now we need to parse this binary "waveform"
    high2low, low2high = [],[]
    for i in range(len(gpiovals)-1):
        if gpiovals[i]==0 and gpiovals[i+1]==1:
            low2high.append(i)
        elif gpiovals[i]==1 and gpiovals[i+1]==0:
            high2low.append(i)
    if len(high2low)!=41 and len(low2high)!=42:
        print("Didn't get all the bites")
        print('len(h2l),len(l2h) = ',len(high2low),len(low2high))
        dtnow = datetime.datetime.utcnow()
        raise ValueError('Missing bite')
        tdate = dtnow.strftime('%Y-%m-%d_%H:%M:%S.%f')
        pickle.dump(gpiovals,open('%s_gpiovals.pkl'%tdate,'wb'))
        print('Saved pickle of data as %s',tdate)
    lowlen = [low2high[i+2] - high2low[i+1] for i in range(40)]
    highlen = [high2low[i+1] - low2high[i+1] for i in range(40)]
    prebitlow = int(sum(lowlen)/40.)
    bits = [int(i > prebitlow) for i in highlen]
    print(bits)
    bin2dec = lambda bindata: int(str('0b' + ''.join(str(i) for i in bindata)),2)
    data_bytes = [bin2dec(bits[i*8:(i+1)*8]) for i in range(5)]
    print(data_bytes)
    # Check checksum
    if sum(data_bytes[0:4]) & 255 != data_bytes[4]:
        print("Data failed checksum")
        raise ValueError('Checksum failed')
    RH = data_bytes[0] + data_bytes[1]/10.
    Temp = data_bytes[2] + data_bytes[3]/10.
    return RH, Temp


def main():
    db_info = pickle.load(open(os.environ['HOME']+'/.mydbinfo.pkl','rb'))
    db = MySQLdb.connect(db_info['host'], db_info['user'], db_info['pass'], 'temps')
    cursor = db.cursor()

    data = []
    for i in range(5):
        try:
            dtnow = datetime.datetime.utcnow()
            # Format into MySQL datetime format
            tdate = dtnow.strftime('%Y-%m-%d %H:%M:%S.%f')
            #db.commit()
            print("Gettin temp/RH %d"%i)
            RH,temp = get_temp_rh()
            data.append((RH,temp))
            print("Temp = %.1fC, RH=%.1f%%"%(temp,RH))
            time.sleep(5)
        except (ValueError):
            time.sleep(5)
        except (KeyboardInterrupt, SystemExit):
            sys.exit()

    temp_avg = sum(i[1] for i in data)/float(len(data))
    RH_avg   = sum(i[0] for i in data)/float(len(data))
    print(temp_avg, RH_avg)
    cursor.execute('insert into testdata values(\"%s\", %.1f, %.1f)'%(tdate,temp_avg,RH_avg))
    db.commit()
    print('Data committed')
    db.close()

if __name__ == '__main__':
    main()
