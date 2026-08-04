package utils

import "fmt"

// ClientError — ошибка 4xx с текстом для клиента.
type ClientError struct {
	Msg string
}

func (e *ClientError) Error() string { return e.Msg }

func NewClientError(msg string) error {
	return &ClientError{Msg: msg}
}

func IsClientError(err error) bool {
	_, ok := err.(*ClientError)
	return ok
}

var (
	ErrBadJSON     = NewClientError("Некорректный JSON")
	ErrUpload      = NewClientError("Не удалось прочитать multipart-запрос")
	ErrNeedText    = NewClientError("Передайте text или file")
	ErrTooLarge    = NewClientError(fmt.Sprintf("Файл слишком большой (лимит %d байт)", MaxUploadBytes))
	ErrReportType  = NewClientError("Тип: client | design | ar | engineering (или 1–4 / ir)")
	ErrUnauthorized = NewClientError("Неверный или отсутствующий API-токен")
	ErrAuthRequired = NewClientError("Задайте FLASK_API_TOKEN / API_TOKEN в .env для доступа не с localhost")
)

// MaxUploadBytes — лимит тела запроса (совпадает с Python MAX_UPLOAD_BYTES).
const MaxUploadBytes = 2_000_000
