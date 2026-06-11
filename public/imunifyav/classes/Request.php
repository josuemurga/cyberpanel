<?php

namespace Imunify360;

use \Imunify360\panels\AbstractPanel;


class Request {
    /**
     * @var AbstractPanel
     */
    private $panel;
    private $commands = array('uploadFile', 'applyLicenseFromPanel', 'installation', 'downgradePlugin');

    public function __construct(AbstractPanel $panel)
    {
        $this->panel = $panel;
    }

    public function handle()
    {
        if ($post = $this->panel->getPost()) {
            $request = (object) $post;
        } else {
            $request = json_decode($this->panel->getJson());
        }

        $this->panel->request = $request;
        if (isset($request->command)
                && in_array($request->command, $this->commands)
                && $this->panel->isAdmin
                && method_exists($this->panel, $request->command)) {
            $this->panel->{$request->command}();
        } else {
            $this->panel->defaultAction();
        }
    }

    public function handle_api()
    {
        $method = $this->get_method_from_url();
        $jwt = $this->get_bearer_token();

        $requestMethod = $_SERVER['REQUEST_METHOD'];
        if ($requestMethod == 'POST' || $requestMethod == 'PATCH' || $requestMethod == 'PUT') {
            // Get POST data
            $postData = json_decode(file_get_contents('php://input'), true);
            $params = isset($postData['params']) ? $postData['params'] : [];
        } elseif ($requestMethod == 'GET' || $requestMethod == 'DELETE') {
            // For GET and DELETE, parameters come from the query string
            $params = $this->get_query_params();
        }

        # Convert to common format
        $args = new \stdClass();
        $args->command = $method;
        $args->params = $params;
        $args->params['remote_addr'] = $_SERVER['REMOTE_ADDR'];
        if ($jwt) {
            $args->params['jwt'] = $jwt;
        }

        try {
            $response = $this->panel->execute(json_encode($args));
            $this->panel->renderSuccess($response);
        } catch (\ErrorException $e) {
            $this->panel->renderError($e->getMessage());
        }
    }


    // Function to get the bearer token from the Authorization header
    public function get_bearer_token() {
        if ( ! function_exists( 'apache_request_headers' ) ) {
            $headers = array();
            $headers['Authorization'] = $_SERVER['HTTP_AUTHORIZATION'];
        }
        else {
            $headers = apache_request_headers();
        }

        if (isset($headers['Authorization'])) {
            $matches = array();
            if (preg_match('/Bearer\s(\S+)/', $headers['Authorization'], $matches)) {
                return $matches[1];
            }
        }

        return null;
    }

    // Function to parse the URL and extract the method
    public function get_method_from_url() {
        // Extract the part of the URL after /api/
        if (preg_match('/\/api\/(.+?)(?:\?|$)/', $_SERVER['REQUEST_URI'], $matches)) {
            $uriParts = explode('/', $matches[1]);

            // Remove empty elements
            $uriParts = array_filter($uriParts);

            return $uriParts;
        }

        return [];
    }

    // Function to get parameters from URL query, handling lists,
    // converting "true"/"false" to booleans, parsing integers,
    // and ensuring specific keys are always arrays
    public function get_query_params() {
        $queryParams = [];
        // Keys that should always be arrays
        $pairs = explode('&', $_SERVER['QUERY_STRING']);

        foreach ($pairs as $pair) {
            if (trim($pair) == '') {
                continue;
            }

            list($key, $value) = explode('=', $pair, 2);
            $value = urldecode($value);

            // Convert "true" and "false" strings to boolean values
            if ($value === "true") {
                $value = true;
            } elseif ($value === "false") {
                $value = false;
            } elseif (is_numeric($value)) {
                // Convert numeric strings to integers
                $value = intval($value);
            }

            // Handle specific keys that should always be arrays
            if ($this->is_array_key($key)) {
                if (isset($queryParams[$key])) {
                    if (!is_array($queryParams[$key])) {
                        $queryParams[$key] = [$queryParams[$key]];
                    }
                    $queryParams[$key][] = $value;
                } else {
                    $queryParams[$key] = [$value];
                }
            } else {
                // For other keys, add or append to the array if key already exists
                if (isset($queryParams[$key])) {
                    if (!is_array($queryParams[$key])) {
                        $queryParams[$key] = [$queryParams[$key]];
                    }
                    $queryParams[$key][] = $value;
                } else {
                    $queryParams[$key] = $value;
                }
            }
        }

        return $queryParams;
    }

    private function is_array_key($key) {
        $arrayKeys = [
            'ids', 'paths', 'users', 'items', 'order_by', 'domains',
            'attachments', 'networks', 'ips', 'by_list', 'by_purpose',
            'scan_ids', 'files', 'by_status'
        ];

        if (in_array($key, $arrayKeys)) {
            return true;
        }

        if ($key == 'purpose') {
            // 'purpose' should be an array for 'ip-list/local/list'
            if (preg_match('/ip-list\/local\/list/', $_SERVER['REQUEST_URI'])) {
                return true;
            }
        }

        return false;
    }

}
