package bridge

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/config"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/models"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/utils"
)

// Client вызывает Python bridge (JSON stdin/stdout).
type Client struct {
	cfg config.Config
}

// New создаёт клиента bridge.
func New(cfg config.Config) *Client {
	return &Client{cfg: cfg}
}

// Call отправляет payload в generate.py и парсит ответ.
func (c *Client) Call(ctx context.Context, payload any) (*models.BridgeResponse, error) {
	if !utils.FileExists(c.cfg.BridgeScript) {
		return nil, fmt.Errorf("bridge script не найден: %s", c.cfg.BridgeScript)
	}

	body, err := json.Marshal(payload)
	if err != nil {
		return nil, err
	}

	ctx, cancel := context.WithTimeout(ctx, 10*time.Minute)
	defer cancel()

	cmd := exec.CommandContext(ctx, c.cfg.PythonBin, c.cfg.BridgeScript)
	cmd.Dir = c.cfg.ProjectRoot
	cmd.Stdin = bytes.NewReader(body)
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	cmd.Env = append(os.Environ(), "PYTHONUNBUFFERED=1")

	runErr := cmd.Run()
	out := strings.TrimSpace(stdout.String())

	var r models.BridgeResponse
	if out != "" {
		if err := json.Unmarshal([]byte(out), &r); err == nil {
			if !r.OK && r.Error != "" {
				return nil, fmt.Errorf("%s", r.Error)
			}
			if r.OK {
				return &r, nil
			}
		}
	}

	if runErr != nil {
		msg := strings.TrimSpace(stderr.String())
		if msg == "" {
			msg = out
		}
		if msg == "" {
			msg = runErr.Error()
		}
		return nil, fmt.Errorf("python bridge failed: %s", msg)
	}

	if err := json.Unmarshal([]byte(out), &r); err != nil {
		return nil, fmt.Errorf("некорректный ответ bridge: %w; raw=%s", err, out)
	}
	return &r, nil
}

// ResolvePath резолвит путь из ответа bridge относительно ProjectRoot.
func (c *Client) ResolvePath(relOrAbs string) (string, error) {
	return utils.ResolveUnderRoot(c.cfg.ProjectRoot, relOrAbs)
}

// BaseName имя файла.
func BaseName(path string) string {
	return filepath.Base(path)
}
