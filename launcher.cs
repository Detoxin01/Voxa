using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Whisper Type")]
[assembly: AssemblyProduct("Whisper Type")]
[assembly: AssemblyDescription("Local push-to-talk voice typing powered by faster-whisper")]
[assembly: AssemblyVersion("1.0.0.0")]

namespace WhisperTypeLauncher
{
    static class Program
    {
        [STAThread]
        static void Main(string[] args)
        {
            string exeDir = AppDomain.CurrentDomain.BaseDirectory;
            string appDir = exeDir;

            if (!File.Exists(Path.Combine(appDir, "whisper_type.py")))
            {
                string pathFile = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "WhisperType",
                    "app_path.txt"
                );
                if (File.Exists(pathFile))
                {
                    appDir = File.ReadAllText(pathFile).Trim();
                }
            }

            string pythonw = Path.Combine(appDir, ".venv", "Scripts", "pythonw.exe");
            string script = Path.Combine(appDir, "whisper_type.py");

            if (!File.Exists(pythonw) || !File.Exists(script))
            {
                MessageBox.Show(
                    "Could not find Whisper Type environment at:\n" + appDir + "\n\nPlease run setup.bat first.",
                    "Whisper Type",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            ProcessStartInfo psi = new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = "\"" + script + "\"",
                WorkingDirectory = appDir,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(psi);
        }
    }
}
