package com.ctone.alarmamqtt.mqtt

import android.os.Build
import android.util.Log
import org.eclipse.paho.client.mqttv3.IMqttActionListener
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.IMqttToken
import org.eclipse.paho.client.mqttv3.MqttAsyncClient
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttException
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import java.nio.charset.StandardCharsets
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicLong

class MqttManager(
    private val onConnectionChanged: (Boolean) -> Unit,
    private val onMessage: (String, String) -> Unit,
    private val onLog: (String) -> Unit,
) {
    companion object {
        private const val TAG = "AlarmaMqtt"
    }

    private var client: MqttAsyncClient? = null
    private var config: MqttConfig? = null
    private val isConnected = AtomicBoolean(false)
    private val connectionToken = AtomicLong(0L)

    fun connect(newConfig: MqttConfig) {
        if (isConnected.get() && config == newConfig) {
            logInfo("Already connected to ${newConfig.serverUri}")
            return
        }

        disconnectInternal(notifyUi = false)

        val clientId = buildClientId()
        val mqttClient = MqttAsyncClient(newConfig.serverUri, clientId, MemoryPersistence())
        val connectToken = connectionToken.incrementAndGet()
        config = newConfig
        client = mqttClient

        mqttClient.setCallback(object : MqttCallbackExtended {
            override fun connectComplete(reconnect: Boolean, serverURI: String?) {
                if (!isCurrentClient(mqttClient, connectToken)) return
                isConnected.set(true)
                onConnectionChanged(true)
                logInfo("MQTT connectComplete reconnect=$reconnect uri=$serverURI")
                subscribeToTopic()
            }

            override fun connectionLost(cause: Throwable?) {
                if (!isCurrentClient(mqttClient, connectToken)) return
                isConnected.set(false)
                onConnectionChanged(false)
                logError("MQTT connection lost: ${cause?.message ?: "unknown"}", cause)
            }

            override fun messageArrived(topic: String?, message: MqttMessage?) {
                if (!isCurrentClient(mqttClient, connectToken)) return
                val payload = message?.payload?.toString(StandardCharsets.UTF_8) ?: ""
                val safeTopic = topic ?: ""
                onMessage(safeTopic, payload)
                logInfo("Mobile RX< topic=$safeTopic payload=$payload qos=${message?.qos}")
            }

            override fun deliveryComplete(deliveryToken: IMqttDeliveryToken?) {
                if (!isCurrentClient(mqttClient, connectToken)) return
                logInfo("Publish delivery complete")
            }
        })

        val options = MqttConnectOptions().apply {
            isAutomaticReconnect = true
            isCleanSession = false
            connectionTimeout = 10
            keepAliveInterval = 30
            if (newConfig.username.isNotBlank()) {
                userName = newConfig.username
                password = newConfig.password.toCharArray()
            }
        }

        try {
            mqttClient.connect(options, null, object : IMqttActionListener {
                override fun onSuccess(asyncActionToken: IMqttToken?) {
                    if (!isCurrentClient(mqttClient, connectToken)) return
                    logInfo("MQTT connect requested: ${newConfig.serverUri}")
                }

                override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                    if (!isCurrentClient(mqttClient, connectToken)) return
                    isConnected.set(false)
                    onConnectionChanged(false)
                    logError("MQTT connect failed: ${exception?.message ?: "unknown error"}", exception)
                }
            })
        } catch (e: MqttException) {
            isConnected.set(false)
            onConnectionChanged(false)
            logError("MQTT connect exception: ${e.message}", e)
        } catch (e: Exception) {
            isConnected.set(false)
            onConnectionChanged(false)
            logError("MQTT connect runtime exception: ${e.message}", e)
        }
    }

    fun publish(payload: String) {
        val currentClient = client
        val currentConfig = config

        if (currentClient == null || currentConfig == null || !isConnected.get() || !currentClient.isConnected) {
            logError("Cannot publish: not connected")
            return
        }

        val normalizedPayload = payload.trim().uppercase(Locale.US)
        if (normalizedPayload != "ON" && normalizedPayload != "OFF") {
            logError("Invalid payload. Use ON or OFF")
            return
        }

        val message = MqttMessage(normalizedPayload.toByteArray(StandardCharsets.UTF_8)).apply {
            qos = currentConfig.qos
            isRetained = false
        }

        try {
            currentClient.publish(currentConfig.topic, message, null, object : IMqttActionListener {
                override fun onSuccess(asyncActionToken: IMqttToken?) {
                    logInfo("Mobile_TX > topic=${currentConfig.topic} payload=$normalizedPayload qos=${currentConfig.qos}")
                }

                override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                    logError("Publish failed: ${exception?.message ?: "unknown error"}", exception)
                }
            })
        } catch (e: MqttException) {
            logError("Publish exception: ${e.message}", e)
        } catch (e: Exception) {
            logError("Publish runtime exception: ${e.message}", e)
        }
    }

    fun disconnect() {
        disconnectInternal(notifyUi = true)
    }

    private fun disconnectInternal(notifyUi: Boolean) {
        val currentClient = client ?: return
        connectionToken.incrementAndGet()
        client = null
        config = null
        isConnected.set(false)

        try {
            if (currentClient.isConnected) {
                currentClient.disconnect(null, object : IMqttActionListener {
                    override fun onSuccess(asyncActionToken: IMqttToken?) {
                        logInfo("MQTT disconnected")
                    }

                    override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                        logError("MQTT disconnect failed: ${exception?.message ?: "unknown error"}", exception)
                    }
                })
            }
        } catch (e: Exception) {
            logError("Disconnect exception: ${e.message}", e)
        }

        try {
            currentClient.close()
        } catch (e: Exception) {
            logError("Close exception: ${e.message}", e)
        }

        if (notifyUi) {
            onConnectionChanged(false)
        }
    }

    fun isClientConnected(): Boolean = isConnected.get()

    private fun isCurrentClient(candidate: MqttAsyncClient, token: Long): Boolean {
        return client === candidate && connectionToken.get() == token
    }

    private fun subscribeToTopic() {
        val currentClient = client
        val currentConfig = config

        if (currentClient == null || currentConfig == null || !isConnected.get() || !currentClient.isConnected) {
            return
        }

        try {
            currentClient.subscribe(currentConfig.topic, currentConfig.qos, null, object : IMqttActionListener {
                override fun onSuccess(asyncActionToken: IMqttToken?) {
                    logInfo("Subscribed: ${currentConfig.topic} qos=${currentConfig.qos}")
                }

                override fun onFailure(asyncActionToken: IMqttToken?, exception: Throwable?) {
                    logError("Subscribe failed: ${exception?.message ?: "unknown error"}", exception)
                }
            })
        } catch (e: MqttException) {
            logError("Subscribe exception: ${e.message}", e)
        } catch (e: Exception) {
            logError("Subscribe runtime exception: ${e.message}", e)
        }
    }

    private fun buildClientId(): String {
        val model = (Build.MODEL ?: "android").replace("\\s+".toRegex(), "_")
        return "alarma_${model}_${System.currentTimeMillis()}"
    }

    private fun logInfo(message: String) {
        onLog(message)
        Log.i(TAG, message)
    }

    private fun logError(message: String, throwable: Throwable? = null) {
        onLog(message)
        if (throwable == null) {
            Log.e(TAG, message)
        } else {
            Log.e(TAG, message, throwable)
        }
    }
}
