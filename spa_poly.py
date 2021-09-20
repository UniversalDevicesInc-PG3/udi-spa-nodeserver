#!/usr/bin/env python3

"""
This is a NodeServer for Balboa Spa written by automationgeek (Jean-Francois Tremblay)
based on the NodeServer template for Polyglot v2 written in Python2/3 by Einstein.42 (James Milne) milne.james@gmail.com
"""

import udi_interface
import pybalboa
import hashlib
import asyncio
import time
import json
import sys
from copy import deepcopy

LOGGER = udi_interface.LOGGER
Custom = udi_interface.Custom
SERVERDATA = json.load(open('server.json'))
VERSION = SERVERDATA['credits'][0]['version']

def get_profile_info(logger):
    pvf = 'profile/version.txt'
    try:
        with open(pvf) as f:
            pv = f.read().replace('\n', '')
    except Exception as err:
        logger.error('get_profile_info: failed to read  file {0}: {1}'.format(pvf,err), exc_info=True)
        pv = 0
    f.close()
    return { 'version': pv }

class Controller(udi_interface.Node):

    def __init__(self, polyglot, primary, address, name):
        super(Controller, self).__init__(polyglot, primary, address, name)
        self.poly = polyglot
        self.name = 'BalboaSpa'
        self.initialized = False
        self.queryON = False
        self.host = ""
        self.hb = 0

        self.CustomParams = Custom(polyglot, 'customparams')

        polyglot.subscribe(polyglot.START, self.start, address)
        polyglot.subscribe(polyglot.CUSTOMPARAMS, self.parameterHandler)
        polyglot.subscribe(polyglot.POLL, self.poll)
        
        polyglot.ready()
        polyglot.addNode(self)

    def parameterHandler(self, params):
        self.poly.Notices.clear()
        try:
            if 'host' in params:
                self.host = params['host']
            else:
                self.host = ""
            
            if self.host == "" :
                LOGGER.error('SPA Balboa requires host parameter to be specified in custom configuration.')
                self.poly.Notices['host'] = 'Please enter the Host/IP address'
                return False
            else:
                self.discover()

        except Exception as ex:
            LOGGER.error('Error starting Balboa NodeServer: %s', str(ex))

    def start(self):
        LOGGER.info('Started Balboa SPA for v2 NodeServer version %s', str(VERSION))
        self.poly.updateProfile()
        self.poly.setCustomParamsDoc()
           
    def poll(self, pollflag):
        if 'longPoll' in pollflag:
            self.heartbeat()
    
    def query(self):
        for node in self.poly.nodes():
            node.reportDrivers()
    
    def heartbeat(self):
        LOGGER.debug('heartbeat: hb={}'.format(self.hb))
        if self.hb == 0:
            self.reportCmd("DON",2)
            self.hb = 1
        else:
            self.reportCmd("DOF",2)
            self.hb = 0

    def discover(self, *args, **kwargs):
        if not self.poly.getNode('spa'):
            self.poly.addNode(Spa(self.poly,self.address,"spa","spa",self.host ))
    
    def delete(self):
        LOGGER.info('Deleting Balboa Spa')

    id = 'controller'
    commands = {
        'QUERY': query,
        'DISCOVER': discover,
    }
    drivers = [{'driver': 'ST', 'value': 1, 'uom': 2}]

class Spa(udi_interface.Node):

    def __init__(self, polyglot, primary, address, name, host):

        super(Spa, self).__init__(polyglot, primary, address, name)
        self.queryON = True
        self.host = host
        polyglot.subscribe(polyglot.POLL, self.update)

    def start(self):
        self.update()

    def setP1(self, command):
        asyncio.run(self._setPump(0,int(command.get('value'))))
        self.setDriver('GV1', int(command.get('value')))
        
    def setP2(self, command):
        asyncio.run(self._setPump(1,int(command.get('value'))))
        self.setDriver('GV2', int(command.get('value')))               
    
    def setTemp(self, command):
        asyncio.run(self._setTemp(int(command.get('value'))))
        self.setDriver('GV6', int(command.get('value')))
    
    def setBlower(self, command):
        if ( int(command.get('value')) == 100 ) :
            val = 1
        else :
            val = 0
        asyncio.run(self._setBlower(val))
        self.setDriver('GV4',int(command.get('value')))
        
    def setCirP(self, command):
        if ( int(command.get('value')) == 100 ) :
            val = 1
        else :
            val = 0
        asyncio.run(self._setPump(0,val))
        self.setDriver('GV3', int(command.get('value')))
    
    def setLight(self, command):
        asyncio.run(self._setLight(int(command.get('value'))))
        self.setDriver('GV5', int(command.get('value')))
                        
    def update(self, pollflag):
        if 'shortPoll' in pollflag:
            asyncio.run(self._getSpaStatus())
            
    def query(self):
        self.reportDrivers()

    async def _getSpaStatus (self) :
        try :
            spa = pybalboa.BalboaSpaWifi(self.host)
            await spa.connect()
            asyncio.ensure_future(spa.listen()) 
            await spa.send_panel_req(0, 1)

            for i in range(0, 30):
                await asyncio.sleep(1)
                if spa.config_loaded:
                    break
                    
            lastupd = 0
            for i in range(0, 3):
                await asyncio.sleep(1)
                if spa.lastupd != lastupd:
                    lastupd = spa.lastupd

            # Temp
            self.setDriver('CLITEMP', spa.get_curtemp())
            self.setDriver('GV6', spa. get_settemp())
               
            # Pump
            self.setDriver('GV1', spa.get_pump(0))
            self.setDriver('GV2', spa.get_pump(1))
            
            if ( spa.get_circ_pump() == 0 ) :
                self.setDriver('GV3',0)
            else :
                self.setDriver('GV3',100)
           
            # Blower
            if ( spa.get_blower(True) == 'Off' ) :
                self.setDriver('GV4',0)
            else :
                self.setDriver('GV4',100)
            
            # Light
            self.setDriver('GV5', spa.get_light(0))
           
            await spa.disconnect()
            return
        except Exception as ex :
            LOGGER.debug ("_setTemp: ", ex )
    
    async def _setTemp(self,temp):
        try:
            spa = pybalboa.BalboaSpaWifi(self.host)
            await spa.connect()
            asyncio.ensure_future(spa.listen())     
            await spa.send_panel_req(0, 1)
            for i in range(0, 30):
                await asyncio.sleep(1)
                if spa.config_loaded:
                    break
            await spa.send_temp_change(temp)
            await spa.disconnect()
        except Exception as ex :
            LOGGER.debug ("_setTemp: ", ex )
        
    async def _setPump(self,pump, setting):
        try:
            spa = pybalboa.BalboaSpaWifi(self.host)
            await spa.connect()
            asyncio.ensure_future(spa.listen())
            await spa.send_panel_req(0, 1)
            for i in range(0, 30):
                await asyncio.sleep(1)
                if spa.config_loaded:
                    break
            await spa.change_pump(pump, setting)
            await spa.disconnect()
        except Exception as ex :
            LOGGER.debug ("_setPump: ", ex )
        return
                        
    async def _setBlower(self,setting):
        try :
            spa = pybalboa.BalboaSpaWifi(self.host)
            await spa.connect()
            asyncio.ensure_future(spa.listen())
            await spa.send_panel_req(0, 1)
            for i in range(0, 30):
                await asyncio.sleep(1)
                if spa.config_loaded:
                    break
            await spa.change_blower(setting)
            await spa.disconnect()
        except Exception as ex :
            LOGGER.debug ("_setBlower: ", ex )
        return
                        
    async def _setLight(self,state):
        spa = pybalboa.BalboaSpaWifi(self.host)
        await spa.connect()
        asyncio.ensure_future(spa.listen())     
        await spa.send_panel_req(0, 1)
        for i in range(0, 30):
            await asyncio.sleep(1)
            if spa.config_loaded:
                break
        await spa.change_light(0,state)
        await spa.disconnect()
                       
    drivers = [{'driver': 'GV1', 'value': 0, 'uom': 25},
               {'driver': 'GV2', 'value': 0, 'uom': 25},
               {'driver': 'GV3', 'value': 0, 'uom': 78},
               {'driver': 'GV4', 'value': 0, 'uom': 78},
               {'driver': 'GV5', 'value': 0, 'uom': 78},
               {'driver': 'GV6', 'value': 0, 'uom': 4},
               {'driver': 'CLITEMP', 'value': 0, 'uom': 4}]

    id = 'spa'
    commands = {
                    'SET_SPEED_P1': setP1,
                    'SET_SPEED_P2': setP2,
                    'SET_TEMP': setTemp,
                    'SET_BLOWER': setBlower,
                    'SET_CIRP': setCirP,
                    'SET_LIGHT': setLight
                }

if __name__ == "__main__":
    try:
        polyglot = udi_interface.Interface([])
        polyglot.start()
        Controller(polyglot, 'controller', 'controller', 'SpaNodeServer')
        polyglot.runForever()
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
