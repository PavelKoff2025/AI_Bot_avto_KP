package app

import (
	"log/slog"
	"net/http"

	"github.com/pavelkoff/ai-auogeneration/go_server/internal/bridge"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/config"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/handlers"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/middleware"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/routes"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/services"
	"github.com/pavelkoff/ai-auogeneration/go_server/internal/utils"
)

// Application — собранное приложение (DI-корень).
type Application struct {
	Cfg     config.Config
	Log     *slog.Logger
	Handler http.Handler
}

// New собирает config → bridge → services → handlers → routes → middleware.
func New(cfg config.Config, log *slog.Logger) *Application {
	if log == nil {
		log = slog.Default()
	}

	bridgeClient := bridge.New(cfg)
	generator := services.NewGenerator(bridgeClient)
	api := handlers.New(log, generator)

	authMW := middleware.APITokenAuth(cfg.APIToken, log)
	mux := routes.NewMux(api, authMW)

	handler := routes.Wrap(
		mux,
		middleware.RequestLogger(log),
		middleware.BodyLimit(utils.MaxUploadBytes),
	)

	return &Application{
		Cfg:     cfg,
		Log:     log,
		Handler: handler,
	}
}
