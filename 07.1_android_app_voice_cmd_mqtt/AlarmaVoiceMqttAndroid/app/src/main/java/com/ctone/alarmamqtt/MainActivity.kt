package com.ctone.alarmamqtt

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.res.ColorStateList
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.speech.RecognizerIntent
import android.text.method.ScrollingMovementMethod
import android.view.MotionEvent
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import android.widget.Toast
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import com.ctone.alarmamqtt.databinding.ActivityMainBinding
import com.ctone.alarmamqtt.mqtt.MqttConfig
import com.ctone.alarmamqtt.mqtt.MqttManager
import com.google.android.material.button.MaterialButton
import com.google.android.material.textfield.TextInputLayout
import java.text.SimpleDateFormat
import java.text.Normalizer
import java.util.Date
import java.util.Locale

class MainActivity : AppCompatActivity() {
    private lateinit var binding: ActivityMainBinding
    private lateinit var mqttManager: MqttManager
    private val uptimeHandler = Handler(Looper.getMainLooper())
    private var appStartElapsedRealtime = 0L
    private var pendingVoiceCommandAfterConnect = false
    private var continuousVoiceModeEnabled = false
    private var voiceRecognizerActive = false
    private var pressedCommandPayload: String? = null
    private var activeCommandPayload: String? = null
    private var confirmedCommandPayload: String? = null
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
    private val voiceRestartRunnable = Runnable {
        if (continuousVoiceModeEnabled && mqttManager.isClientConnected() && !voiceRecognizerActive) {
            startVoiceRecognizer()
        }
    }
    private val voiceCommandLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult(),
    ) { result ->
        voiceRecognizerActive = false

        if (result.resultCode != Activity.RESULT_OK) {
            if (continuousVoiceModeEnabled) {
                appendLog("Voice recognizer ended, restarting")
                scheduleNextVoiceRecognizerLaunch()
            }
            return@registerForActivityResult
        }

        val spokenPhrases = result.data
            ?.getStringArrayListExtra(RecognizerIntent.EXTRA_RESULTS)
            .orEmpty()

        handleVoiceResults(spokenPhrases)

        if (continuousVoiceModeEnabled) {
            scheduleNextVoiceRecognizerLaunch()
        }
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
                runOnUiThread {
                    updateConnectionUi(connected)
                    if (connected && pendingVoiceCommandAfterConnect) {
                        pendingVoiceCommandAfterConnect = false
                        appendLog("MQTT ready for voice command")
                        startVoiceRecognizer()
                    } else if (connected && continuousVoiceModeEnabled && !voiceRecognizerActive) {
                        appendLog("MQTT reconnected, resuming continuous voice command")
                        scheduleNextVoiceRecognizerLaunch()
                    }
                }
            },
            onMessage = { topic, payload ->
                runOnUiThread {
                    binding.tvLastMessage.text = getString(R.string.last_message_template, topic, payload)
                    syncCommandButtonsWithPayload(payload)
                }
            },
            onLog = { line ->
                runOnUiThread { appendLog(line) }
            },
            onPublishResult = { payload, success ->
                runOnUiThread {
                    handlePublishResult(payload, success)
                }
            },
        )

        cacheOriginalTextColors()
        restoreForm()
        setupActions()
        updateConnectionUi(false)
        renderCommandButtons()
        autoConnect()
        handleExternalIntent(intent)
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

    override fun onNewIntent(intent: Intent?) {
        super.onNewIntent(intent)
        setIntent(intent)
        handleExternalIntent(intent)
    }

    override fun onDestroy() {
        stopContinuousVoiceMode()
        super.onDestroy()
        mqttManager.disconnect()
    }

    private fun setupActions() {
        binding.btnConnect.setOnClickListener {
            val config = readConfigFromForm() ?: return@setOnClickListener
            mqttManager.connect(config)
        }

        binding.btnDisconnect.setOnClickListener {
            pendingVoiceCommandAfterConnect = false
            stopContinuousVoiceMode()
            mqttManager.disconnect()
        }

        binding.btnPublishOn.setOnClickListener {
            publishCommand(PAYLOAD_ARM)
        }

        binding.btnPublishOff.setOnClickListener {
            publishCommand(PAYLOAD_DISARM)
        }

        binding.btnPublishOn.setOnTouchListener { _, event ->
            handleCommandButtonTouch(PAYLOAD_ARM, event)
        }

        binding.btnPublishOff.setOnTouchListener { _, event ->
            handleCommandButtonTouch(PAYLOAD_DISARM, event)
        }

        binding.btnClearLog.setOnClickListener {
            binding.tvLog.text = ""
        }

        binding.btnVoiceCommand.setOnClickListener {
            toggleContinuousVoiceCommand()
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
        binding.btnVoiceCommand.alpha = 1f

        if (!connected) {
            pressedCommandPayload = null
            activeCommandPayload = null
            confirmedCommandPayload = null
            voiceRecognizerActive = false
        }
        renderCommandButtons()
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

    private fun toggleContinuousVoiceCommand() {
        if (continuousVoiceModeEnabled) {
            stopContinuousVoiceMode(logReason = "manual")
            toast(getString(R.string.voice_command_loop_stopped))
            return
        }

        continuousVoiceModeEnabled = true
        appendLog("Continuous voice command started")
        launchVoiceCommand()
    }

    private fun launchVoiceCommand() {
        if (mqttManager.isClientConnected()) {
            startVoiceRecognizer()
            return
        }

        val config = readConfigFromForm() ?: return
        pendingVoiceCommandAfterConnect = true
        toast(getString(R.string.voice_command_auto_connect))
        appendLog("Auto-connect for voice command to ${config.serverUri}")
        mqttManager.connect(config)
    }

    private fun startVoiceRecognizer() {
        if (!continuousVoiceModeEnabled || voiceRecognizerActive) {
            return
        }

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ro-RO")
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "ro-RO")
            putExtra(RecognizerIntent.EXTRA_PROMPT, getString(R.string.voice_command_prompt))
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                putExtra(RecognizerIntent.EXTRA_PREFER_OFFLINE, false)
            }
        }

        try {
            voiceRecognizerActive = true
            voiceCommandLauncher.launch(intent)
        } catch (_: ActivityNotFoundException) {
            voiceRecognizerActive = false
            pendingVoiceCommandAfterConnect = false
            stopContinuousVoiceMode()
            toast(getString(R.string.voice_command_not_supported))
            appendLog("Voice command unavailable on this device")
        }
    }

    private fun scheduleNextVoiceRecognizerLaunch() {
        uptimeHandler.removeCallbacks(voiceRestartRunnable)
        uptimeHandler.postDelayed(voiceRestartRunnable, VOICE_RESTART_DELAY_MS)
    }

    private fun stopContinuousVoiceMode(logReason: String? = null) {
        continuousVoiceModeEnabled = false
        pendingVoiceCommandAfterConnect = false
        voiceRecognizerActive = false
        uptimeHandler.removeCallbacks(voiceRestartRunnable)
        if (logReason != null) {
            appendLog("Continuous voice command stopped ($logReason)")
        }
    }

    private fun handleExternalIntent(intent: Intent?) {
        if (intent?.action != ACTION_STOP_VOICE_LOOP) {
            return
        }
        stopContinuousVoiceMode(logReason = "external-intent")
        toast(getString(R.string.voice_command_loop_stopped))
    }

    private fun handleVoiceResults(spokenPhrases: List<String>) {
        val firstMatch = spokenPhrases
            .firstOrNull { it.isNotBlank() }
            ?.trim()

        if (firstMatch != null) {
            appendLog(getString(R.string.voice_command_heard, firstMatch))
        }

        val payload = spokenPhrases
            .asSequence()
            .mapNotNull { mapVoicePhraseToPayload(it) }
            .firstOrNull()

        if (payload == null) {
            toast(getString(R.string.voice_command_no_match))
            appendLog("Voice command not recognized")
            return
        }

        publishCommand(payload)
        toast(getString(R.string.voice_command_sent, payload))
    }

    private fun publishCommand(payload: String) {
        val normalizedPayload = payload.normalizePayloadOrNull() ?: return
        activeCommandPayload = normalizedPayload
        renderCommandButtons()
        mqttManager.publish(normalizedPayload)
    }

    private fun handlePublishResult(payload: String, success: Boolean) {
        pressedCommandPayload = null
        val normalizedPayload = payload.normalizePayloadOrNull()
        if (success && normalizedPayload != null) {
            confirmedCommandPayload = normalizedPayload
            activeCommandPayload = normalizedPayload
        } else {
            activeCommandPayload = confirmedCommandPayload
        }
        renderCommandButtons()
    }

    private fun syncCommandButtonsWithPayload(payload: String) {
        val normalizedPayload = payload.normalizePayloadOrNull() ?: return
        pressedCommandPayload = null
        confirmedCommandPayload = normalizedPayload
        activeCommandPayload = normalizedPayload
        renderCommandButtons()
    }

    private fun handleCommandButtonTouch(payload: String, event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                pressedCommandPayload = payload.normalizePayloadOrNull()
                renderCommandButtons()
            }

            MotionEvent.ACTION_UP,
            MotionEvent.ACTION_CANCEL -> {
                pressedCommandPayload = null
                renderCommandButtons()
            }
        }
        return false
    }

    private fun renderCommandButtons() {
        val onVisualState: CommandButtonVisualState
        val offVisualState: CommandButtonVisualState

        if (pressedCommandPayload != null) {
            onVisualState = if (pressedCommandPayload == PAYLOAD_ARM) {
                CommandButtonVisualState.PRESSED
            } else {
                CommandButtonVisualState.INACTIVE
            }
            offVisualState = if (pressedCommandPayload == PAYLOAD_DISARM) {
                CommandButtonVisualState.PRESSED
            } else {
                CommandButtonVisualState.INACTIVE
            }
        } else {
            onVisualState = if (activeCommandPayload == PAYLOAD_ARM) {
                CommandButtonVisualState.ACTIVE_ON
            } else {
                CommandButtonVisualState.INACTIVE
            }
            offVisualState = if (activeCommandPayload == PAYLOAD_DISARM) {
                CommandButtonVisualState.ACTIVE_OFF
            } else {
                CommandButtonVisualState.INACTIVE
            }
        }

        applyCommandButtonStyle(binding.btnPublishOn, onVisualState)
        applyCommandButtonStyle(binding.btnPublishOff, offVisualState)
    }

    private fun applyCommandButtonStyle(button: MaterialButton, state: CommandButtonVisualState) {
        val backgroundColor = when (state) {
            CommandButtonVisualState.INACTIVE -> R.color.command_button_inactive
            CommandButtonVisualState.PRESSED,
            CommandButtonVisualState.ACTIVE_ON -> R.color.command_button_green_neon
            CommandButtonVisualState.ACTIVE_OFF -> R.color.command_button_off_active
        }

        val textColor = when (state) {
            CommandButtonVisualState.INACTIVE -> R.color.command_button_text_light
            CommandButtonVisualState.PRESSED,
            CommandButtonVisualState.ACTIVE_ON,
            CommandButtonVisualState.ACTIVE_OFF -> R.color.command_button_text_dark
        }

        button.backgroundTintList = ColorStateList.valueOf(
            ContextCompat.getColor(this, backgroundColor),
        )
        button.strokeColor = ColorStateList.valueOf(
            ContextCompat.getColor(this, R.color.command_button_stroke),
        )
        button.setTextColor(ContextCompat.getColor(this, textColor))
    }

    private fun mapVoicePhraseToPayload(phrase: String): String? {
        val normalized = normalizeVoiceText(phrase)
        return when {
            normalized.contains("DEZARMEAZA") || normalized.contains("DEZACTIVEAZA") ||
                normalized.contains("DISARM") || normalized.contains("OPRESTE ALARMA") ||
                normalized.contains("OFF") -> PAYLOAD_DISARM

            normalized.contains("ARMEAZA") || normalized.contains("ACTIVEAZA") ||
                normalized.contains("ARM") || normalized.contains("PORNESTE ALARMA") ||
                normalized.contains("ON") -> PAYLOAD_ARM

            else -> null
        }
    }

    private fun normalizeVoiceText(value: String): String {
        val decomposed = Normalizer.normalize(value, Normalizer.Form.NFD)
        return decomposed
            .replace("\\p{M}+".toRegex(), "")
            .uppercase(Locale.ROOT)
    }

    private fun String.normalizePayloadOrNull(): String? {
        return when (trim().uppercase(Locale.US)) {
            PAYLOAD_ARM -> PAYLOAD_ARM
            PAYLOAD_DISARM -> PAYLOAD_DISARM
            else -> null
        }
    }

    companion object {
        private const val GREEN_FLASH_DURATION_MS = 3000L
        private const val VOICE_RESTART_DELAY_MS = 350L
        const val ACTION_STOP_VOICE_LOOP = "com.ctone.alarmamqtt.action.STOP_VOICE_LOOP"
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
        private const val PAYLOAD_ARM = "ARMEAZA"
        private const val PAYLOAD_DISARM = "DEZARMEAZA"
    }

    private enum class CommandButtonVisualState {
        INACTIVE,
        PRESSED,
        ACTIVE_ON,
        ACTIVE_OFF,
    }
}
