import os
import sys
import time
from pathlib import Path
import logging

# Configure logging to see LSP output
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Add current dir to path to import VNCode modules
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from core import start_csharp_lsp, stop_csharp_lsp, get_lsp_suggestions
import api as api_module

def setup_dummy_project():
    """Create a dummy C# project for csharp-ls to analyze."""
    project_dir = Path("csharp_demo_project")
    project_dir.mkdir(exist_ok=True)
    
    # Create simple csproj
    csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0</TargetFramework>
    <ImplicitUsings>enable</ImplicitUsings>
    <Nullable>enable</Nullable>
  </PropertyGroup>
</Project>
"""
    with open(project_dir / "csharp_demo_project.csproj", "w", encoding="utf-8") as f:
        f.write(csproj_content)
        
    # Create simple Program.cs
    program_content = """using System;

namespace Demo
{
    class Program
    {
        static void Main(string[] args)
        {
            string message = "Hello from VNCode!";
            Console.WriteLine(message);
            
            // We will request autocomplete after the dot
            DateTime.
        }
    }
}
"""
    file_path = project_dir / "Program.cs"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(program_content)
        
    return str(file_path.absolute()), program_content, str(project_dir.absolute())

def cleanup_dummy_project(project_dir):
    """Remove dummy project files."""
    import shutil
    try:
        if os.path.exists(project_dir):
            shutil.rmtree(project_dir)
            print("Cleaned up dummy project directory.")
    except Exception as e:
        print(f"Error during cleanup: {e}")

def main():
    print("=" * 60)
    print("C# LSP Integration Test Demo")
    print("=" * 60)
    
    # 1. Setup dummy files
    file_path, code, project_root = setup_dummy_project()
    print(f"Created dummy C# project at: {project_root}")
    
    # 2. Try starting C# LSP
    print("\nStarting C# LSP (csharp-ls)...")
    success = start_csharp_lsp(server_path="csharp-ls", project_root=project_root)
    
    if not success:
        print("\n❌ Failed to start C# LSP server.")
        print("Please make sure you have installed csharp-ls by running:")
        print("  dotnet tool install -g csharp-ls")
        cleanup_dummy_project(project_root)
        sys.exit(1)
        
    print("✅ C# LSP Server started successfully!")
    
    try:
        client = api_module.get_csharp_client()
        
        # Wait a moment for LSP server to fully index the project
        print("Waiting 3 seconds for server indexing...")
        time.sleep(3)
        
        # 3. Test completions after "DateTime."
        # "DateTime." is at the end of the file. Cursor position:
        cursor_pos = code.find("DateTime.") + len("DateTime.")
        
        print(f"\nRequesting completions at cursor position: {cursor_pos}")
        suggestions = get_lsp_suggestions(
            language="c#",
            prefix="",
            code=code,
            cursor_pos=cursor_pos,
            file_path=file_path
        )
        
        print("\n--- LSP Autocomplete Suggestions ---")
        if suggestions:
            for s in suggestions[:15]:
                print(f" - {s}")
            if len(suggestions) > 15:
                print(f" ... and {len(suggestions) - 15} more items")
        else:
            print("No suggestions returned.")
            
        # 4. Test hover info on "Console"
        # "Console" is in Console.WriteLine
        console_pos = code.find("Console")
        lines_before = code[:console_pos].split('\n')
        line = len(lines_before) - 1
        char = len(lines_before[-1])
        
        print(f"\nRequesting hover info for 'Console' at line {line + 1}, char {char + 1}...")
        hover = client.get_hover_info(file_path, line, char)
        
        print("\n--- LSP Hover Info ---")
        if hover:
            print(hover.strip())
        else:
            print("No hover info returned.")
            
    finally:
        # 5. Shutdown LSP server
        print("\nStopping C# LSP Server...")
        stop_csharp_lsp()
        print("Server stopped.")
        
        # 6. Cleanup files
        cleanup_dummy_project(project_root)
        print("\nTest completed.")

if __name__ == "__main__":
    main()
