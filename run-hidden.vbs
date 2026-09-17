' 콘솔 창 없이 run.bat을 실행한다. 작업 스케줄러(로그온 시)에서 wscript.exe로 호출.
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir
sh.Run "cmd /c """ & dir & "\run.bat""", 0, False
