const aedes = require('aedes')();
const server = require('net').createServer(aedes.handle);
const httpServer = require('http').createServer();
const ws = require('websocket-stream');

const mqttPort = 1883;
const wsPort = 8888; // Port untuk koneksi dari Browser

// Broker MQTT Standar
server.listen(mqttPort, function () {
    console.log('MQTT Broker running on port:', mqttPort);
});

// Broker via WebSocket (Penting untuk Browser)
ws.createServer({ server: httpServer }, aedes.handle);
httpServer.listen(wsPort, function () {
    console.log('MQTT Broker via WebSocket running on port:', wsPort);
});

aedes.on('client', function (client) {
    console.log('Client Connected: \x1b[33m' + (client ? client.id : client) + '\x1b[0m');
});

aedes.on('publish', function (packet, client) {
    if (client) {
        console.log('Message from client ' + client.id + ' : ' + packet.payload.toString());
    }
});