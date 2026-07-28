@echo off
rem ttyd shim for VHS on Windows.
rem
rem Injects an absolute working directory into every ttyd invocation.

rem MARK: Why This Exists
rem VHS spawns ttyd without the -w flag.
rem ttyd 1.7.7 on Windows then hands CreateProcessW an invalid working directory, which fails with error 267.
rem VHS never reads ttyd's stderr and has no startup timeout, so it waits forever for a terminal that never starts and prints nothing.
rem See https://github.com/tsl0922/ttyd/issues/1292 and https://github.com/charmbracelet/vhs/issues/631.
rem
rem Put this directory first on PATH and VHS picks up the shim instead of ttyd itself.
rem PATHEXT makes Go resolve ttyd.cmd for a bare `ttyd` lookup.
rem
rem This file is the same workaround posted upstream, so it hardcodes nothing about this repository.
setlocal

rem MARK: Real Binary
rem Find the actual executable, asking for the .exe explicitly so this shim never matches itself.
set "ttydExe="
for /f "delims=" %%I in ('where ttyd.exe 2^>nul') do if not defined ttydExe set "ttydExe=%%I"

rem Fail loudly rather than letting VHS hang on a missing dependency.
if not defined ttydExe (
	echo ttyd.exe was not found on PATH. Install it with `scoop install ttyd`.
	exit /b 1
)

rem MARK: Dispatch
rem %CD% is the absolute directory VHS was launched from, which is also what the tape's relative paths resolve against.
rem ttyd rejects relative paths and ~, so -w must receive a full absolute path.
"%ttydExe%" -w "%CD%" %*
