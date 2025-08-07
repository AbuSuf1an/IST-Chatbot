<?php
/**
 * Plugin Name: IST Chatbot
 * Plugin URI: https://github.com/AbuSuf1an/IST-Chatbot
 * Description: AI-powered chatbot widget for Institute of Science and Technology that helps students, faculty, and staff with IST-related questions.
 * Version: 1.0.0
 * Author: AbuSuf1an
 * Author URI: https://github.com/AbuSuf1an
 * License: GPL v2 or later
 * Text Domain: ist-chatbot
 */

// Prevent direct access
if (!defined('ABSPATH')) {
    exit;
}

class ISTChatbot {
    
    /**
     * Plugin version
     */
    const VERSION = '1.0.0';
    
    /**
     * Plugin directory path
     */
    private $plugin_path;
    
    /**
     * Plugin directory URL
     */
    private $plugin_url;
    
    /**
     * Initialize the plugin
     */
    public function __construct() {
        $this->plugin_path = plugin_dir_path(__FILE__);
        $this->plugin_url = plugin_dir_url(__FILE__);
        
        add_action('init', array($this, 'init'));
    }
    
    /**
     * Initialize plugin functionality
     */
    public function init() {
        // Add hooks
        add_action('wp_enqueue_scripts', array($this, 'enqueue_scripts'));
        add_action('wp_footer', array($this, 'render_chatbot_widget'));
        add_action('admin_menu', array($this, 'add_admin_menu'));
        add_action('admin_init', array($this, 'register_settings'));
        
        // Add AJAX handlers for admin
        add_action('wp_ajax_test_ist_chatbot_api', array($this, 'test_api_connection'));
        
        // Load text domain for translations
        load_plugin_textdomain('ist-chatbot', false, dirname(plugin_basename(__FILE__)) . '/languages');
    }
    
    /**
     * Enqueue CSS and JavaScript files
     */
    public function enqueue_scripts() {
        // Only load on frontend and if enabled
        if (is_admin() || !$this->is_chatbot_enabled()) {
            return;
        }
        
        // Enqueue CSS
        wp_enqueue_style(
            'ist-chatbot-style',
            $this->plugin_url . 'assets/css/chatbot.css',
            array(),
            self::VERSION
        );
        
        // Enqueue JavaScript
        wp_enqueue_script(
            'ist-chatbot-script',
            $this->plugin_url . 'assets/js/chatbot.js',
            array(),
            self::VERSION,
            true
        );
        
        // Localize script with settings
        wp_localize_script('ist-chatbot-script', 'istChatbotConfig', array(
            'apiUrl' => $this->get_api_url(),
            'enabled' => $this->is_chatbot_enabled(),
            'botName' => get_option('ist_chatbot_name', 'IST Assistant'),
            'welcomeMessage' => get_option('ist_chatbot_welcome', 'Hello! I\'m here to help with IST-related questions.'),
            'nonce' => wp_create_nonce('ist_chatbot_nonce')
        ));
    }
    
    /**
     * Render the chatbot widget HTML
     */
    public function render_chatbot_widget() {
        if (!$this->is_chatbot_enabled()) {
            return;
        }
        
        // The widget HTML is created by JavaScript
        echo '<!-- IST Chatbot Widget will be inserted here by JavaScript -->';
    }
    
    /**
     * Add admin menu page
     */
    public function add_admin_menu() {
        add_options_page(
            __('IST Chatbot Settings', 'ist-chatbot'),
            __('IST Chatbot', 'ist-chatbot'),
            'manage_options',
            'ist-chatbot-settings',
            array($this, 'admin_page')
        );
    }
    
    /**
     * Register plugin settings
     */
    public function register_settings() {
        // General settings
        register_setting('ist_chatbot_settings', 'ist_chatbot_enabled');
        register_setting('ist_chatbot_settings', 'ist_chatbot_api_url');
        register_setting('ist_chatbot_settings', 'ist_chatbot_name');
        register_setting('ist_chatbot_settings', 'ist_chatbot_welcome');
        
        // API settings
        add_settings_section(
            'ist_chatbot_api_section',
            __('API Configuration', 'ist-chatbot'),
            array($this, 'api_section_callback'),
            'ist_chatbot_settings'
        );
        
        add_settings_field(
            'ist_chatbot_enabled',
            __('Enable Chatbot', 'ist-chatbot'),
            array($this, 'enabled_field_callback'),
            'ist_chatbot_settings',
            'ist_chatbot_api_section'
        );
        
        add_settings_field(
            'ist_chatbot_api_url',
            __('API URL', 'ist-chatbot'),
            array($this, 'api_url_field_callback'),
            'ist_chatbot_settings',
            'ist_chatbot_api_section'
        );
        
        // Appearance settings
        add_settings_section(
            'ist_chatbot_appearance_section',
            __('Appearance', 'ist-chatbot'),
            array($this, 'appearance_section_callback'),
            'ist_chatbot_settings'
        );
        
        add_settings_field(
            'ist_chatbot_name',
            __('Bot Name', 'ist-chatbot'),
            array($this, 'name_field_callback'),
            'ist_chatbot_settings',
            'ist_chatbot_appearance_section'
        );
        
        add_settings_field(
            'ist_chatbot_welcome',
            __('Welcome Message', 'ist-chatbot'),
            array($this, 'welcome_field_callback'),
            'ist_chatbot_settings',
            'ist_chatbot_appearance_section'
        );
    }
    
    /**
     * Admin page HTML
     */
    public function admin_page() {
        ?>
        <div class="wrap">
            <h1><?php _e('IST Chatbot Settings', 'ist-chatbot'); ?></h1>
            
            <div class="notice notice-info">
                <p><?php _e('Configure your IST Chatbot settings below. Make sure your backend API is running and accessible.', 'ist-chatbot'); ?></p>
            </div>
            
            <form method="post" action="options.php">
                <?php
                settings_fields('ist_chatbot_settings');
                do_settings_sections('ist_chatbot_settings');
                submit_button();
                ?>
            </form>
            
            <div class="card">
                <h2><?php _e('API Connection Test', 'ist-chatbot'); ?></h2>
                <p><?php _e('Test the connection to your chatbot API:', 'ist-chatbot'); ?></p>
                <button type="button" id="test-api-connection" class="button button-secondary">
                    <?php _e('Test API Connection', 'ist-chatbot'); ?>
                </button>
                <div id="api-test-result" style="margin-top: 10px;"></div>
            </div>
        </div>
        
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            document.getElementById('test-api-connection').addEventListener('click', function() {
                const button = this;
                const result = document.getElementById('api-test-result');
                
                button.disabled = true;
                button.textContent = '<?php _e('Testing...', 'ist-chatbot'); ?>';
                result.innerHTML = '';
                
                fetch(ajaxurl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: 'action=test_ist_chatbot_api&_wpnonce=<?php echo wp_create_nonce('ist_chatbot_test'); ?>'
                })
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        result.innerHTML = '<div class="notice notice-success inline"><p>' + data.data.message + '</p></div>';
                    } else {
                        result.innerHTML = '<div class="notice notice-error inline"><p>' + data.data.message + '</p></div>';
                    }
                })
                .catch(error => {
                    result.innerHTML = '<div class="notice notice-error inline"><p><?php _e('Connection test failed:', 'ist-chatbot'); ?> ' + error.message + '</p></div>';
                })
                .finally(() => {
                    button.disabled = false;
                    button.textContent = '<?php _e('Test API Connection', 'ist-chatbot'); ?>';
                });
            });
        });
        </script>
        <?php
    }
    
    /**
     * Section callbacks
     */
    public function api_section_callback() {
        echo '<p>' . __('Configure the connection to your IST Chatbot backend API.', 'ist-chatbot') . '</p>';
    }
    
    public function appearance_section_callback() {
        echo '<p>' . __('Customize the appearance and messages of your chatbot.', 'ist-chatbot') . '</p>';
    }
    
    /**
     * Field callbacks
     */
    public function enabled_field_callback() {
        $enabled = get_option('ist_chatbot_enabled', false);
        echo '<input type="checkbox" name="ist_chatbot_enabled" value="1" ' . checked(1, $enabled, false) . ' />';
        echo '<label for="ist_chatbot_enabled">' . __('Enable the chatbot widget on your website', 'ist-chatbot') . '</label>';
    }
    
    public function api_url_field_callback() {
        $api_url = get_option('ist_chatbot_api_url', 'http://localhost:8001/api/chat');
        echo '<input type="url" name="ist_chatbot_api_url" value="' . esc_attr($api_url) . '" class="regular-text" />';
        echo '<p class="description">' . __('The URL of your IST Chatbot API endpoint', 'ist-chatbot') . '</p>';
    }
    
    public function name_field_callback() {
        $name = get_option('ist_chatbot_name', 'IST Assistant');
        echo '<input type="text" name="ist_chatbot_name" value="' . esc_attr($name) . '" class="regular-text" />';
    }
    
    public function welcome_field_callback() {
        $welcome = get_option('ist_chatbot_welcome', 'Hello! I\'m here to help with IST-related questions.');
        echo '<textarea name="ist_chatbot_welcome" rows="3" class="large-text">' . esc_textarea($welcome) . '</textarea>';
    }
    
    /**
     * Test API connection
     */
    public function test_api_connection() {
        // Verify nonce
        if (!wp_verify_nonce($_POST['_wpnonce'], 'ist_chatbot_test')) {
            wp_die(__('Security check failed', 'ist-chatbot'));
        }
        
        $api_url = $this->get_health_check_url();
        
        $response = wp_remote_get($api_url, array(
            'timeout' => 10,
            'headers' => array(
                'Content-Type' => 'application/json',
            )
        ));
        
        if (is_wp_error($response)) {
            wp_send_json_error(array(
                'message' => __('Failed to connect to API: ', 'ist-chatbot') . $response->get_error_message()
            ));
        }
        
        $status_code = wp_remote_retrieve_response_code($response);
        $body = wp_remote_retrieve_body($response);
        
        if ($status_code === 200) {
            $data = json_decode($body, true);
            wp_send_json_success(array(
                'message' => __('API connection successful! Status: ', 'ist-chatbot') . ($data['status'] ?? 'OK')
            ));
        } else {
            wp_send_json_error(array(
                'message' => __('API returned error status: ', 'ist-chatbot') . $status_code
            ));
        }
    }
    
    /**
     * Check if chatbot is enabled
     */
    private function is_chatbot_enabled() {
        return get_option('ist_chatbot_enabled', false);
    }
    
    /**
     * Get API URL
     */
    private function get_api_url() {
        return get_option('ist_chatbot_api_url', 'http://localhost:8001/api/chat');
    }
    
    /**
     * Get health check URL
     */
    private function get_health_check_url() {
        $api_url = $this->get_api_url();
        return str_replace('/api/chat', '/health', $api_url);
    }
}

// Initialize the plugin
new ISTChatbot();

// Activation hook
register_activation_hook(__FILE__, function() {
    // Set default options
    add_option('ist_chatbot_enabled', false);
    add_option('ist_chatbot_api_url', 'http://localhost:8001/api/chat');
    add_option('ist_chatbot_name', 'IST Assistant');
    add_option('ist_chatbot_welcome', 'Hello! I\'m the IST chatbot assistant. I\'m here to help you with questions about Institute of Science and Technology. What would you like to know?');
});

// Deactivation hook
register_deactivation_hook(__FILE__, function() {
    // Clean up if needed
});

// Uninstall hook
register_uninstall_hook(__FILE__, function() {
    // Remove options
    delete_option('ist_chatbot_enabled');
    delete_option('ist_chatbot_api_url');
    delete_option('ist_chatbot_name');
    delete_option('ist_chatbot_welcome');
});

?>
