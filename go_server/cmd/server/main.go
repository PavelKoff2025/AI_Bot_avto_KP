package main

import (
	"fmt"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"time"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/app"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/config"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/dotenv"
)

func main() {
	loadDotEnv()

	log := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	cfg, err := config.Load()
	if err != nil {
		log.Error("config", "err", err)
		os.Exit(1)
	}

	application := app.New(cfg, log)

	httpServer := &http.Server{
		Addr:              cfg.Addr(),
		Handler:           application.Handler,
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       15 * time.Minute,
		WriteTimeout:      15 * time.Minute,
		IdleTimeout:       60 * time.Second,
	}

	log.Info("Go API server starting",
		"addr", "http://"+cfg.Addr(),
		"project_root", cfg.ProjectRoot,
		"python", cfg.PythonBin,
		"bridge", cfg.BridgeScript,
		"auth", cfg.APIToken != "",
	)

	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Error("server stopped", "err", err)
		os.Exit(1)
	}
}

func loadDotEnv() {
	candidates := []string{".env"}
	if wd, err := os.Getwd(); err == nil {
		candidates = append(candidates,
			filepath.Join(wd, ".env"),
			filepath.Join(wd, "..", ".env"),
			filepath.Join(wd, "..", "..", ".env"),
		)
	}
	seen := map[string]struct{}{}
	for _, p := range candidates {
		abs, err := filepath.Abs(p)
		if err != nil {
			continue
		}
		if _, ok := seen[abs]; ok {
			continue
		}
		seen[abs] = struct{}{}
		if err := dotenv.Load(abs); err == nil {
			fmt.Fprintf(os.Stderr, "loaded env: %s\n", abs)
			return
		}
	}
}
