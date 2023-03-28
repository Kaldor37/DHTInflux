from setuptools import find_packages, setup

setup(
    name='dhtinflux',
    version='0.1.0',
    description='DHT data to InfluxDB',
    url='https://github.com/Kaldor37/DHTInflux',
    author='Kaldor37',
    author_email='davy.gabard@gmail.com',
    packages=find_packages(),
    install_requires=[
        'influxdb>=5.3',
        'adafruit-circuitpython-dht>=3.7.8',
        'RPi.GPIO>=0.7'
    ]
)
