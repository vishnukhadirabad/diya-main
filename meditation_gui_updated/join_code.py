import multiprocessing
import os


# Function to run the first program: handles camera integration
def run_program1():
    os.system("python3 all_cameras_integration.py")


# Function to run the second program: handles motor movement
def run_program2():
    os.system("python3 termination_time.py")


# Entry point for the multiprocessing script
if __name__ == "__main__":
    # Create two separate processes for camera integration and motor movement
    p1 = multiprocessing.Process(target=run_program1)
    p2 = multiprocessing.Process(target=run_program2)

    # Start both processes
    p1.start()
    p2.start()

    # Wait for both processes to complete before exiting the main program
    p1.join()
    p2.join()
