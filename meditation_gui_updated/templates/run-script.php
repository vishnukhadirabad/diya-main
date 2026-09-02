<?php
// Define the path to the acquisition Bash script
$script_path = '/home/dadn/Desktop/meditation_gui/meditation_visualRohan/sequence9';  // Adjust the path if necessary

// Check if the file exists and is executable
if (file_exists($script_path) && is_executable($script_path)) {
    // Run the script
    $output = shell_exec($script_path);
    echo "Script executed successfully!";
} else {
    echo "Error: Script not found or not executable.";
}
?>

