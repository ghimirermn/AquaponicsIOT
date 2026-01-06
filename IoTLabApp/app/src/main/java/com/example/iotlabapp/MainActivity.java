package com.example.iotlabapp;

import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.TextView;
import android.widget.Button;
import android.widget.Switch;
import android.widget.Toast;
import android.graphics.Color;

import androidx.appcompat.app.AppCompatActivity;
import androidx.cardview.widget.CardView;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity {

    // ========== CONFIGURATION ==========
    // Change this to your Windows PC's IP address
    private static final String API_BASE_URL = "http://100.87.59.95:8000";
    private static final int REFRESH_INTERVAL_MS = 5000; // 5 seconds
    // ===================================

    // UI Elements - Sensor displays
    private TextView tvWaterTemp, tvAirTemp, tvPH, tvDO, tvAmmonia;
    private TextView tvWaterLevel, tvEC, tvHumidity, tvLight;
    private TextView tvDiagnosis, tvPumpStatus, tvLastUpdate;
    private Button btnRefresh;
    private Switch switchAutoRefresh;
    private CardView cardStatus;

    // UI Elements - Control buttons
    private Button btnPumpToggle, btnLightToggle, btnSimulateFailure;
    private boolean isFailureSimulated = false;

    // Background execution
    private ExecutorService executor;
    private Handler mainHandler;
    private Runnable autoRefreshRunnable;
    private boolean isAutoRefreshEnabled = true;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        // Initialize executor for background tasks
        executor = Executors.newSingleThreadExecutor();
        mainHandler = new Handler(Looper.getMainLooper());

        // Initialize UI elements
        initializeViews();

        // Setup button click listeners
        setupClickListeners();

        // Initial data fetch
        fetchSensorData();

        // Start auto-refresh
        startAutoRefresh();
    }

    private void initializeViews() {
        // Sensor displays
        tvWaterTemp = findViewById(R.id.tvWaterTemp);
        tvAirTemp = findViewById(R.id.tvAirTemp);
        tvPH = findViewById(R.id.tvPH);
        tvDO = findViewById(R.id.tvDO);
        tvAmmonia = findViewById(R.id.tvAmmonia);
        tvWaterLevel = findViewById(R.id.tvWaterLevel);
        tvEC = findViewById(R.id.tvEC);
        tvHumidity = findViewById(R.id.tvHumidity);
        tvLight = findViewById(R.id.tvLight);
        tvDiagnosis = findViewById(R.id.tvDiagnosis);
        tvPumpStatus = findViewById(R.id.tvPumpStatus);
        tvLastUpdate = findViewById(R.id.tvLastUpdate);
        btnRefresh = findViewById(R.id.btnRefresh);
        switchAutoRefresh = findViewById(R.id.switchAutoRefresh);
        cardStatus = findViewById(R.id.cardStatus);

        // Control buttons
        btnPumpToggle = findViewById(R.id.btnPumpToggle);
        btnLightToggle = findViewById(R.id.btnLightToggle);
        btnSimulateFailure = findViewById(R.id.btnSimulateFailure);
    }

    private void setupClickListeners() {
        // Refresh button
        btnRefresh.setOnClickListener(v -> fetchSensorData());

        // Auto-refresh toggle
        switchAutoRefresh.setOnCheckedChangeListener((buttonView, isChecked) -> {
            isAutoRefreshEnabled = isChecked;
            if (isChecked) {
                startAutoRefresh();
            } else {
                stopAutoRefresh();
            }
        });

        // Pump toggle button
        btnPumpToggle.setOnClickListener(v -> {
            sendControlCommand("/control/pump", "toggle");
            Toast.makeText(this, "Toggling pump...", Toast.LENGTH_SHORT).show();
        });

        // Light toggle button
        btnLightToggle.setOnClickListener(v -> {
            sendControlCommand("/control/light", "toggle");
            Toast.makeText(this, "Toggling light...", Toast.LENGTH_SHORT).show();
        });

        // Simulate failure button
        btnSimulateFailure.setOnClickListener(v -> {
            isFailureSimulated = !isFailureSimulated;
            sendFailureSimulation(isFailureSimulated);
            btnSimulateFailure.setText(isFailureSimulated ? "Stop Failure" : "Simulate Failure");
            btnSimulateFailure.setBackgroundColor(isFailureSimulated ? 
                Color.parseColor("#4ecca3") : Color.parseColor("#e94560"));
            Toast.makeText(this, 
                isFailureSimulated ? "Pump failure simulated!" : "Failure simulation stopped", 
                Toast.LENGTH_SHORT).show();
        });
    }

    private void startAutoRefresh() {
        autoRefreshRunnable = new Runnable() {
            @Override
            public void run() {
                if (isAutoRefreshEnabled) {
                    fetchSensorData();
                    mainHandler.postDelayed(this, REFRESH_INTERVAL_MS);
                }
            }
        };
        mainHandler.postDelayed(autoRefreshRunnable, REFRESH_INTERVAL_MS);
    }

    private void stopAutoRefresh() {
        if (autoRefreshRunnable != null) {
            mainHandler.removeCallbacks(autoRefreshRunnable);
        }
    }

    private void fetchSensorData() {
        executor.execute(() -> {
            try {
                URL url = new URL(API_BASE_URL + "/latest");
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("GET");
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);

                int responseCode = connection.getResponseCode();
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    BufferedReader reader = new BufferedReader(
                            new InputStreamReader(connection.getInputStream())
                    );
                    StringBuilder response = new StringBuilder();
                    String line;
                    while ((line = reader.readLine()) != null) {
                        response.append(line);
                    }
                    reader.close();

                    JSONObject data = new JSONObject(response.toString());
                    updateUI(data);
                } else {
                    showError("Server returned: " + responseCode);
                }
                connection.disconnect();
            } catch (Exception e) {
                showError("Error: " + e.getMessage());
            }
        });
    }

    private void sendControlCommand(String endpoint, String state) {
        executor.execute(() -> {
            try {
                URL url = new URL(API_BASE_URL + endpoint + "?state=" + state);
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);

                int responseCode = connection.getResponseCode();
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    // Command sent successfully
                    mainHandler.post(() -> fetchSensorData()); // Refresh to see changes
                }
                connection.disconnect();
            } catch (Exception e) {
                mainHandler.post(() -> 
                    Toast.makeText(this, "Control error: " + e.getMessage(), Toast.LENGTH_SHORT).show()
                );
            }
        });
    }

    private void sendFailureSimulation(boolean enable) {
        executor.execute(() -> {
            try {
                URL url = new URL(API_BASE_URL + "/control/simulate-failure?enable=" + enable);
                HttpURLConnection connection = (HttpURLConnection) url.openConnection();
                connection.setRequestMethod("POST");
                connection.setConnectTimeout(5000);
                connection.setReadTimeout(5000);

                int responseCode = connection.getResponseCode();
                if (responseCode == HttpURLConnection.HTTP_OK) {
                    mainHandler.post(() -> fetchSensorData());
                }
                connection.disconnect();
            } catch (Exception e) {
                mainHandler.post(() -> 
                    Toast.makeText(this, "Simulation error: " + e.getMessage(), Toast.LENGTH_SHORT).show()
                );
            }
        });
    }

    private void updateUI(JSONObject data) {
        mainHandler.post(() -> {
            try {
                if (data.has("message")) {
                    tvDiagnosis.setText(data.getString("message"));
                    return;
                }

                // Update all sensor values
                tvWaterTemp.setText(String.format("%.1f°C", data.getDouble("water_temp_C")));
                tvAirTemp.setText(String.format("%.1f°C", data.getDouble("air_temp_C")));
                tvPH.setText(String.format("%.2f", data.getDouble("pH")));
                tvDO.setText(String.format("%.2f mg/L", data.getDouble("dissolved_oxygen_mgL")));
                tvAmmonia.setText(String.format("%.3f mg/L", data.getDouble("ammonia_mgL")));
                tvWaterLevel.setText(String.format("%.1f%%", data.getDouble("water_level_percent")));
                tvEC.setText(String.format("%.1f µS/cm", data.getDouble("ec_uScm")));
                tvHumidity.setText(String.format("%.1f%%", data.getDouble("humidity_percent")));
                tvLight.setText(String.format("%.0f lux", data.getDouble("light_lux")));

                // Update diagnosis and status
                String diagnosis = data.optString("diagnosis", "Unknown");
                tvDiagnosis.setText(diagnosis);

                String pumpStatus = data.optString("pump_status", "Unknown");
                tvPumpStatus.setText("Pump: " + pumpStatus);

                // Update pump toggle button text based on status
                if (pumpStatus.equals("ON")) {
                    btnPumpToggle.setText("Pump: ON");
                    btnPumpToggle.setBackgroundColor(Color.parseColor("#4ecca3"));
                } else if (pumpStatus.equals("OFF")) {
                    btnPumpToggle.setText("Pump: OFF");
                    btnPumpToggle.setBackgroundColor(Color.parseColor("#ff9800"));
                } else {
                    btnPumpToggle.setText("Pump: FAILURE");
                    btnPumpToggle.setBackgroundColor(Color.parseColor("#e94560"));
                }

                // Update light toggle button
                String lightStatus = data.optString("light_status", "OFF");
                btnLightToggle.setText("Light: " + lightStatus);
                btnLightToggle.setBackgroundColor(lightStatus.equals("ON") ? 
                    Color.parseColor("#ffd700") : Color.parseColor("#555555"));

                // Update status card color based on diagnosis
                if (diagnosis.equals("Normal operation")) {
                    cardStatus.setCardBackgroundColor(Color.parseColor("#4ecca3"));
                    tvDiagnosis.setTextColor(Color.parseColor("#1a1a2e"));
                } else {
                    cardStatus.setCardBackgroundColor(Color.parseColor("#e94560"));
                    tvDiagnosis.setTextColor(Color.WHITE);
                }

                // Update timestamp
                String timestamp = data.optString("timestamp", "N/A");
                tvLastUpdate.setText("Last update: " + timestamp);

            } catch (Exception e) {
                tvDiagnosis.setText("Parse error: " + e.getMessage());
            }
        });
    }

    private void showError(String message) {
        mainHandler.post(() -> {
            tvDiagnosis.setText(message);
            cardStatus.setCardBackgroundColor(Color.parseColor("#666666"));
        });
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        stopAutoRefresh();
        if (executor != null) {
            executor.shutdown();
        }
    }
}