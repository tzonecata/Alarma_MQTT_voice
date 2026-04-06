package com.ctone.alarmamqtt.mqtt

data class MqttConfig(
    val host: String,
    val port: Int,
    val username: String,
    val password: String,
    val topic: String,
    val qos: Int = 1,
) {
    val serverUri: String
        get() = "tcp://$host:$port"
}
