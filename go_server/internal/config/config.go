package config

import (
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/utils"
)

// Config — настройки HTTP-сервера и Python bridge.
type Config struct {
	Host         string
	Port         int
	APIToken     string
	ProjectRoot  string
	PythonBin    string
	BridgeScript string
}

// Addr возвращает host:port.
func (c Config) Addr() string {
	return c.Host + ":" + strconv.Itoa(c.Port)
}

// Load читает конфигурацию из окружения.
func Load() (Config, error) {
	root := strings.TrimSpace(os.Getenv("PROJECT_ROOT"))
	if root == "" {
		wd, err := os.Getwd()
		if err != nil {
			return Config{}, err
		}
		cand := wd
		for i := 0; i < 4; i++ {
			if utils.FileExists(filepath.Join(cand, "utils", "report_service.py")) {
				root = cand
				break
			}
			if filepath.Base(cand) == "go_server" {
				root = filepath.Dir(cand)
				break
			}
			parent := filepath.Dir(cand)
			if parent == cand {
				break
			}
			cand = parent
		}
		if root == "" {
			root = filepath.Dir(wd)
		}
	}

	python := strings.TrimSpace(os.Getenv("PYTHON_BIN"))
	if python == "" {
		venv := filepath.Join(root, ".venv", "bin", "python")
		if utils.FileExists(venv) {
			python = venv
		} else {
			python = "python3"
		}
	}

	bridgeScript := strings.TrimSpace(os.Getenv("BRIDGE_SCRIPT"))
	if bridgeScript == "" {
		bridgeScript = filepath.Join(root, "go_server", "bridge", "generate.py")
	}

	port := 5001
	if v := strings.TrimSpace(os.Getenv("GO_SERVER_PORT")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			port = n
		}
	} else if v := strings.TrimSpace(os.Getenv("PORT")); v != "" {
		if n, err := strconv.Atoi(v); err == nil && n > 0 {
			port = n
		}
	}

	host := strings.TrimSpace(os.Getenv("GO_SERVER_HOST"))
	if host == "" {
		host = "127.0.0.1"
	}

	token := strings.TrimSpace(os.Getenv("FLASK_API_TOKEN"))
	if token == "" {
		token = strings.TrimSpace(os.Getenv("API_TOKEN"))
	}

	return Config{
		Host:         host,
		Port:         port,
		APIToken:     token,
		ProjectRoot:  root,
		PythonBin:    python,
		BridgeScript: bridgeScript,
	}, nil
}
