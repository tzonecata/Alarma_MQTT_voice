package com.ctone.alarmamqtt

import android.content.res.ColorStateList
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.text.method.ScrollingMovementMethod
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.ctone.alarmamqtt.databinding.ActivityMainBinding
import com.ctone.alarmamqtt.mqtt.MqttConfig
import com.ctone.alarmamqtt.mqtt.MqttManager
import com.google.android.material.textfield.TextInputLayout
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var mqttManager: MqttManager
    private val uptimeHandler = Handler(Looper.getMainLooper())
    private var appStartElapsedRealtime = 0L
    private val originalTextColors = mutableMapOf<TextView, ColorStateList>()
    private val originalHintColors = mutableMapOf<TextInputLayout, Pair<ColorStateList?, ColorStateList?>>()

    private val prefs by lazy { getSharedPreferences(PREFS_NAME, MODE_PRIVATE) }
    private val timestampFormat = SimpleDateFormat("HH:mm:ss", Locale.US)
    private val uptimeTicker = object : Runnable {
        override fun run() {
            renderUptime()
            uptimeHandler.postDelayed(this, 1000L)
        }
    }
    private val restoreTextColorsRunnable = Runnable {
        restoreOriginalTextColors()
        binding.tvAppUptime.setTextColor(ContextCompat.getColor(this, R.color.tzone_green_bright))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        appStartElapsedRealtime = SystemClock.elapsedRealtime()
        renderUptime()

        binding.tvLog.movementMethod = ScrollingMovementMethod()

        mqttManager = MqttManager(
            onConnectionChanged = { connected ->
                runOnUiThread { updateConnectionUi(connected) }
            },
            onMessage = { topic, payload ->
                runOnUiThread {
                    binding.tvLastMessage.text = getString(R.string.last_message_template, topic, payload)
                }
            },
            onLog = { line ->
                runOnUiThread { appendLog(line) }
            },
        )

        cacheOriginalTextColors()
        restoreForm()
        setupActions()
        updateConnectionUi(false)
        autoConnect()
    }

    override fun onStart() {
        super.onStart()
        uptimeHandler.post(uptimeTicker)
    }

    override fun onStop() {
        super.onStop()
        uptimeHandler.removeCallbacks(uptimeTicker)
        uptimeHandler.removeCallbacks(restoreTextColorsRunnable)
    }

    override fun onPause() {
        super.onPause()
        saveForm()
    }

    override fun onDestroy() {
        super.onDestroy()
        mqttManager.disconnect()
    }

    private fun setupActions() {
        binding.btnConnect.setOnClickListener {
            val config = readConfigFromForm() ?: return@setOnClickListener
            mqttManager.connect(config)
        }

        binding.btnDisconnect.setOnClickListener {
            mqttManager.disconnect()
        }

        binding.btnPublishOn.setOnClickListener {
            mqttManager.publish("ON")
        }

        binding.btnPublishOff.setOnClickListener {
            mqttManager.publish("OFF")
        }

        binding.btnClearLog.setOnClickListener {
            binding.tvLog.text = ""
        }

        binding.tvBrandTzone.setOnClickListener {
            appStartElapsedRealtime = SystemClock.elapsedRealtime()
            renderUptime()
            applyGreenFlash()
            appendLog("Uptime reset")
        }
    }

    private fun applyGreenFlash() {
        val green = ContextCompat.getColor(this, R.color.tzone_green_bright)
        applyTextColorRecursively(binding.root, green)
        uptimeHandler.removeCallbacks(restoreTextColorsRunnable)
        uptimeHandler.postDelayed(restoreTextColorsRunnable, GREEN_FLASH_DURATION_MS)
    }

    private fun cacheOriginalTextColors() {
        originalTextColors.clear()
        originalHintColors.clear()
        cacheTextColorsRecursively(binding.root)
    }

    private fun cacheTextColorsRecursively(view: View) {
        when (view) {
            is TextInputLayout -> originalHintColors[view] = view.defaultHintTextColor to view.hintTextColor
            is TextView -> originalTextColors[view] = view.textColors
        }

        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                cacheTextColorsRecursively(view.getChildAt(i))
            }
        }
    }

    private fun restoreOriginalTextColors() {
        originalHintColors.forEach { (til, colors) ->
            til.defaultHintTextColor = colors.first
            til.hintTextColor = colors.second
        }
        originalTextColors.forEach { (textView, colors) ->
            textView.setTextColor(colors)
        }
    }

    private fun applyTextColorRecursively(view: View, color: Int) {
        when (view) {
            is TextInputLayout -> {
                val colorStateList = ColorStateList.valueOf(color)
                view.defaultHintTextColor = colorStateList
                view.hintTextColor = colorStateList
            }
            is TextView -> view.setTextColor(color)
        }

        if (view is ViewGroup) {
            for (i in 0 until view.childCount) {
                applyTextColorRecursively(view.getChildAt(i), color)
            }
        }
    }

    private fun renderUptime() {
        val totalSeconds = ((SystemClock.elapsedRealtime() - appStartElapsedRealtime) / 1000).coerceAtLeast(0)
        val hours = totalSeconds / 3600
        val minutes = (totalSeconds % 3600) / 60
        val seconds = totalSeconds % 60
        binding.tvAppUptime.text = getString(
            R.string.brand_uptime_template,
            hours,
            minutes,
            seconds,
        )
    }

    private fun readConfigFromForm(): MqttConfig? {
        val host = binding.etBrokerHost.text.toString().trim()
        val portText = binding.etBrokerPort.text.toString().trim()
        val username = binding.etUsername.text.toString().trim()
        val password = binding.etPassword.text.toString()
        val topic = binding.etTopic.text.toString().trim()

        if (host.isEmpty()) {
            toast("Broker host is required")
            return null
        }
        if (portText.isEmpty()) {
            toast("Broker port is required")
            return null
        }
        if (topic.isEmpty()) {
            toast("Topic is required")
            return null
        }

        val port = portText.toIntOrNull()
        if (port == null || port !in 1..65535) {
            toast("Broker port must be 1..65535")
            return null
        }

        return MqttConfig(
            host = host,
            port = port,
            username = username,
            password = password,
            topic = topic,
            qos = 1,
        )
    }

    private fun updateConnectionUi(connected: Boolean) {
        binding.tvConnectionState.text = if (connected) {
            getString(R.string.connection_state_connected)
        } else {
            getString(R.string.connection_state_disconnected)
        }

        binding.btnConnect.isEnabled = !connected
        binding.btnDisconnect.isEnabled = connected
        binding.btnPublishOn.isEnabled = connected
        binding.btnPublishOff.isEnabled = connected
    }

    private fun appendLog(line: String) {
        val timestamp = timestampFormat.format(Date())
        val current = binding.tvLog.text.toString()
        val next = if (current.isEmpty()) {
            "[$timestamp] $line"
        } else {
            "$current\n[$timestamp] $line"
        }
        binding.tvLog.text = next

        val layout = binding.tvLog.layout ?: return
        val scrollAmount = layout.getLineTop(binding.tvLog.lineCount) - binding.tvLog.height
        if (scrollAmount > 0) {
            binding.tvLog.scrollTo(0, scrollAmount)
        } else {
            binding.tvLog.scrollTo(0, 0)
        }
    }

    private fun restoreForm() {
        binding.etBrokerHost.setText(prefs.getString(KEY_HOST, DEFAULT_HOST))
        binding.etBrokerPort.setText(prefs.getInt(KEY_PORT, DEFAULT_PORT).toString())
        binding.etUsername.setText(prefs.getString(KEY_USERNAME, DEFAULT_USERNAME))
        binding.etPassword.setText(prefs.getString(KEY_PASSWORD, DEFAULT_PASSWORD))
        binding.etTopic.setText(prefs.getString(KEY_TOPIC, DEFAULT_TOPIC))
    }

    private fun saveForm() {
        val port = binding.etBrokerPort.text.toString().toIntOrNull() ?: DEFAULT_PORT
        prefs.edit()
            .putString(KEY_HOST, binding.etBrokerHost.text.toString().trim())
            .putInt(KEY_PORT, port)
            .putString(KEY_USERNAME, binding.etUsername.text.toString().trim())
            .putString(KEY_PASSWORD, binding.etPassword.text.toString())
            .putString(KEY_TOPIC, binding.etTopic.text.toString().trim())
            .apply()
    }

    private fun toast(text: String) {
        Toast.makeText(this, text, Toast.LENGTH_SHORT).show()
    }

    private fun autoConnect() {
        val config = readConfigFromForm() ?: return
        appendLog("Auto-connect to ${config.serverUri}")
        mqttManager.connect(config)
    }

    companion object {
        private const val GREEN_FLASH_DURATION_MS = 3000L
        private const val PREFS_NAME = "mqtt_form"

        private const val KEY_HOST = "host"
        private const val KEY_PORT = "port"
        private const val KEY_USERNAME = "username"
        private const val KEY_PASSWORD = "password"
        private const val KEY_TOPIC = "topic"

        private const val DEFAULT_HOST = "192.168.1.100"
        private const val DEFAULT_PORT = 18883
        private const val DEFAULT_USERNAME = "mqttuser"
        private const val DEFAULT_PASSWORD = "mqttpass"
        private const val DEFAULT_TOPIC = "control_status_relay"
    }
}
