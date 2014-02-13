#!/usr/bin/env python
# -*- coding: utf-8 -*-

from pushover import pushover     # https://github.com/pix0r/pushover
import paho.mqtt.client as paho   # pip install paho-mqtt
import logging
import signal
import sys
import time
import os

__author__    = 'Jan-Piet Mens <jpmens()gmail.com>, Ben Jones <ben.jones12()gmail.com>'
__copyright__ = 'Copyright 2014 Jan-Piet Mens'
__license__   = """Eclipse Public License - v 1.0 (http://www.eclipse.org/legal/epl-v10.html)"""

# script name (without extension) used for config/logfile names
SCRIPTNAME = os.path.splitext(os.path.basename(__file__))[0]

CONFIGFILE = os.getenv(SCRIPTNAME.upper() + 'CONF', SCRIPTNAME + '.conf')
LOGFILE    = os.getenv(SCRIPTNAME.upper() + 'LOG', SCRIPTNAME + '.log')

# load configuration
conf = {}
try:
    execfile(CONFIGFILE, conf)
except Exception, e:
    print "Cannot load %s: %s" % (CONFIGFILE, str(e))
    sys.exit(2)

LOGLEVEL = conf.get('loglevel', logging.DEBUG)
LOGFORMAT = conf.get('logformat', '%(asctime)-15s %(message)s')

MQTT_HOST = conf.get('broker', 'localhost')
MQTT_PORT = int(conf.get('port', 1883))
MQTT_LWT = conf.get('lwt', None)

# initialise logging    
logging.basicConfig(filename=LOGFILE, level=LOGLEVEL, format=LOGFORMAT)
logging.info("Starting %s" % SCRIPTNAME)
logging.info("INFO MODE")
logging.debug("DEBUG MODE")

# initialise MQTT broker connection
mqttc = paho.Client('mqtt2pushover', clean_session=False)

# check for authentication
if conf['username'] is not None:
    mqttc.username_pw_set(conf['username'], conf['password'])

if MQTT_LWT is not None:
    # configure the last-will-and-testament
    mqttc.will_set(MQTT_LWT, payload="mqtt2pushover", qos=0, retain=False)

def connect():
    """
    Connect to the broker
    """
    logging.debug("Attempting connection to MQTT broker %s:%d..." % (MQTT_HOST, MQTT_PORT))
    mqttc.on_connect = on_connect
    mqttc.on_message = on_message
    mqttc.on_disconnect = on_disconnect

    try:
        result = mqttc.connect(MQTT_HOST, MQTT_PORT, 60)
        if result == 0:
            mqttc.loop_forever()
        else:
            logging.info("Connection failed with error code %s. Retrying in 10s...", result)
            time.sleep(10)
            connect()
    except Exception, e:
        logging.error("Cannot connect to MQTT broker at %s:%d: %s" % (MQTT_HOST, MQTT_PORT, str(e)))
        sys.exit(2)
         
def disconnect(signum, frame):
    """
    Signal handler to ensure we disconnect cleanly 
    in the event of a SIGTERM or SIGINT.
    """
    logging.debug("Disconnecting from MQTT broker...")
    mqttc.loop_stop()
    mqttc.disconnect()
    logging.debug("Exiting on signal %d", signum)
    sys.exit(signum)

def on_connect(mosq, userdata, result_code):
    logging.debug("Connected to MQTT broker, subscribing to topics...")
    for topic in conf['topicuser'].keys():
        logging.debug("Subscribing to %s" % topic)
        mqttc.subscribe(topic, 0)

def on_message(mosq, userdata, msg):
    """
    Message received from the broker
    """
    topic = msg.topic
    payload = str(msg.payload)
    logging.debug("Message received on %s: %s" % (topic, payload))
    
    users = None
    title = "Info"
    priority = "-1"

    params = {
            'retry' : 60,
            'expire' : 3600,
        }

    # Try to find matching settings for this topic
    for sub in conf['topicuser']:
        if paho.topic_matches_sub(sub, topic):
            try:
                users = conf['topicuser'][sub]
            except:
                logging.info("Cannot find userkeys for topic %s" % topic)
                return
            break

    # Set title if configured; else pushover.net defaults
    for sub in conf['topictitle']:
        if paho.topic_matches_sub(sub, topic):
            try:
                title = conf['topictitle'][sub]
                params['title'] = title
            except:
                pass
            break

    # Set priority if configured; else pushover.net defaults
    for sub in conf['topicpriority']:
        if paho.topic_matches_sub(sub, topic):
            try:
                priority = conf['topicpriority'][sub]
                params['priority'] = priority
            except:
                pass
            break

    for user in users:
        logging.debug("Sending pushover notification to %s [%s]..." % (user, params))
        userkey = conf['pushoveruser'][user][0]
        appkey = conf['pushoveruser'][user][1]
        try:
            pushover(
                message=payload, 
                user=userkey, token=appkey, 
                **params)
            logging.debug("Successfully sent notification")
        except Exception, e:
            logging.warn("Notification failed: %s" % str(e))

def on_disconnect(mosq, userdata, result_code):
    """
    Handle disconnections from the broker
    """
    if result_code == 0:
        logging.info("Clean disconnection")
    else:
        logging.info("Unexpected disconnection! Reconnecting in 5 seconds...")
        logging.debug("Result code: %s", result_code)
        time.sleep(5)
        connect()

# use the signal module to handle signals
signal.signal(signal.SIGTERM, disconnect)
signal.signal(signal.SIGINT, disconnect)
        
# connect to broker and start listening
connect()
