import configparser
import logging
import os.path
import signal
import time
from datetime import datetime
from typing import Dict, Any

import adafruit_dht
import board
from adafruit_dht import DHTBase
from influxdb import InfluxDBClient
from influxdb.exceptions import InfluxDBServerError


class DHTInflux:
    """
    Reads DHT data and writes in an InfluxDB measurement
    """

    _CONF_FILE_NAME = 'dhtinflux.conf'

    def __init__(self):
        self._config = configparser.ConfigParser()

        if os.path.isfile(f'/etc/{self._CONF_FILE_NAME}'):
            self._config.read(f'/etc/{self._CONF_FILE_NAME}')

        elif os.path.isfile(f'/etc/dhtinflux/{self._CONF_FILE_NAME}'):
            self._config.read(f'/etc/dhtinflux/{self._CONF_FILE_NAME}')

        elif os.path.isfile(self._CONF_FILE_NAME):
            self._config.read(self._CONF_FILE_NAME)

        logging.basicConfig(
            filename=self._config.get('logging', 'file', fallback='dhtinflux.log'),
            level=getattr(logging, self._config.get('logging', 'level', fallback='INFO').upper()),
            format=self._config.get('logging', 'format', fallback='%(asctime)s [%(levelname)s] %(message)s')
        )

        self._influx_client = InfluxDBClient(
            host=self._config.get('database', 'host', fallback='localhost'),
            port=self._config.getint('database', 'port', fallback=8086),
            username=self._config.get('database', 'username', fallback='dhtinflux'),
            password=self._config.get('database', 'password', fallback='dhtinflux')
        )
        self._influx_database = self._config.get('database', 'database_name', fallback='dhtinflux')
        self._influx_write_attemps = self._config.getint('database', 'write_attempts', fallback=3)

        signal.signal(signal.SIGINT, self._sig_handler)
        signal.signal(signal.SIGTERM, self._sig_handler)

        self._gpio_pin_name = self._config.get('sensor', 'gpio_pin', fallback='D3')
        self._sensor_name = self._config.get('sensor', 'name', fallback='DHT22')
        self._measurement_interval = self._config.getint('sensor', 'measurement_interval', fallback=30)

        gpio_pin = getattr(board, self._gpio_pin_name)
        self._adafruit_sensor: DHTBase = getattr(adafruit_dht, self._sensor_name)(gpio_pin)
        self._running = True

    def _sig_handler(self, signo, _sigframe):
        logging.info(f'Received stop signal: {signo}')
        self._running = False

    def run(self):
        logging.info('Running')

        if not self._influx_client.ping():
            logging.error('Failed to ping InfluxDB')
            exit(1)

        if self._influx_database not in self._influx_client.get_list_database():
            self._influx_client.create_database(self._influx_database)

        self._influx_client.switch_database(self._influx_database)

        while self._running:
            measurement = {
                'sensor': self._sensor_name,
                'gpio_pin': self._gpio_pin_name,
                'temperature': self._adafruit_sensor.temperature,
                'humidity': self._adafruit_sensor.humidity
            }
            logging.debug(f'Read DHT: {measurement}')
            self._write_measurement('dht', datetime.utcnow().isoformat(), measurement)
            time.sleep(self._measurement_interval)

        logging.info('Done')

    def _write_measurement(
        self, measurement_name: str, utc_time: str, fields: Dict[str, Any], tags: Dict[str, Any] = None
    ):
        """
        Writes any measurement to DB
        :param measurement_name: name of the measurement
        :param utc_time: time (UTC) of the measurement to write as iso formatted string
        :param fields: fields in the measurement
        :return: True on success
        """
        for __ in range(self._influx_write_attemps):
            try:
                measurement_data = {
                    'measurement': measurement_name,
                    'time': utc_time,
                    'fields': fields
                }
                if tags:
                    measurement_data['tags'] = tags

                if self._influx_client.write_points([measurement_data]):
                    return True

            except InfluxDBServerError as ex:
                logging.warning(f'Failed to write measurement {measurement_name}: {ex} - {fields}')

            time.sleep(0.1)

        logging.error(
            f'Failed to write measurement {measurement_name} within {self._influx_write_attemps} attempts: {fields}'
        )
        return False
