import logging
import multiprocessing
import time

import paho.mqtt.client as mqtt

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        pass

    try:
        import unicodedata
        unicodedata.numeric(s)
        return True
    except (TypeError, ValueError):
        pass

    return False

class MQTTClient(multiprocessing.Process):
    def __init__(self, messageQ, commandQ, config):
        self.logger = logging.getLogger('RFLinkGW.MQTTClient')
        self.logger.info("Starting...")

        multiprocessing.Process.__init__(self)
        self.__messageQ = messageQ
        self.__commandQ = commandQ

        self.mqttDataPrefix = config['mqtt_prefix']
        self.mqttDataFormat = config['mqtt_format']
        self._mqttConn = mqtt.Client(client_id='RFLinkGateway')
        self._mqttConn.username_pw_set(config['mqtt_user'], config['mqtt_password'])
        self._mqttConn.connect(config['mqtt_host'], port=config['mqtt_port'], keepalive=120)
        self._mqttConn.on_disconnect = self._on_disconnect
        self._mqttConn.on_publish = self._on_publish
        self._mqttConn.on_message = self._on_message

    def close(self):
        self.logger.info("Closing connection")
        self._mqttConn.disconnect()

    def _on_disconnect(self, client, userdata, rc):
        if rc != 0:
            self.logger.error("Unexpected disconnection.")
            self._mqttConn.reconnect()

    def _on_publish(self, client, userdata, mid):
        self.logger.debug("Message " + str(mid) + " published.")

    def _on_message(self, client, userdata, message):
        self.logger.debug("Message received: %s" % (message))

        data = message.topic.replace(self.mqttDataPrefix + "/", "").split("/")
        data_out = {
            'method': 'subscribe',
            'topic': message.topic,
            'family': data[0],
            'deviceId': data[1],
            'param': data[3],
            'payload': message.payload.decode('ascii'),
            'qos': 1
        }
        self.__commandQ.put(data_out)

    def publish(self, task):
        topic = "%s/%s" % (self.mqttDataPrefix, task['topic'])
  
        if self.mqttDataFormat == 'json':
            if is_number(task['payload']):
                task['payload'] = '{"value": ' + str(task['payload']) + '}'
            else:
                task['payload'] = '{"value": "' + str(task['payload']) + '"}'
        try:
            msg_info = self._mqttConn.publish(topic, payload=task['payload'])
            self.logger.debug('Sending:%s' % (task))
            if msg_info.is_published() == False:
                self.logger.debug('Failed.. wait for publish')
                #msg_info.wait_for_publish()

        except Exception as e:
            self.logger.error('Publish problem: %s' % (e))
            self.__messageQ.put(task)

    def run(self):
        self._mqttConn.subscribe("%s/+/+/W/+" % self.mqttDataPrefix)
        while True:
            if not self.__messageQ.empty():
                task = self.__messageQ.get()
                if task['method'] == 'publish':
                    self.publish(task)
            else:
                time.sleep(0.01)
            self._mqttConn.loop()
            if self._mqttConn.is_connected() == False:
                self.logger.debug('Try to reconnecting..')
                try:
                    self._mqttConn.reconnect()
                except Exception as e:
                    self.logger.debug('Failed, wait and try again.')
                    time.sleep(5)
