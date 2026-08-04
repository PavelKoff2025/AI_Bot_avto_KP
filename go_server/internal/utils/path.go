package utils

import (
	"os"
	"path/filepath"
)

// FileExists — обычный файл существует.
func FileExists(path string) bool {
	st, err := os.Stat(path)
	return err == nil && !st.IsDir()
}

// ResolveUnderRoot резолвит относительный путь относительно root (или cwd).
func ResolveUnderRoot(root, relOrAbs string) (string, error) {
	if relOrAbs == "" {
		return "", NewClientError("пустой путь к файлу")
	}
	if filepath.IsAbs(relOrAbs) {
		return relOrAbs, nil
	}
	p := filepath.Join(root, relOrAbs)
	if FileExists(p) {
		return p, nil
	}
	wd, _ := os.Getwd()
	p2 := filepath.Join(wd, relOrAbs)
	if FileExists(p2) {
		return p2, nil
	}
	return p, nil
}

// AbsJoin склеивает root + rel, если rel не абсолютный.
func AbsJoin(root, rel string) string {
	if filepath.IsAbs(rel) {
		return rel
	}
	return filepath.Join(root, rel)
}
