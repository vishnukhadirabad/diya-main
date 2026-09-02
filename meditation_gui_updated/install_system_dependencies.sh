#!/bin/bash

echo "Updating package list..."

sudo apt update

echo "Installing system dependencies..."

sudo apt install -y \
    python3-dev \
    build-essential \
    cmake \
    git \
    curl \
    wget \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgtk2.0-dev \
    libgtk-3-dev \
    libboost-all-dev \
    libopenblas-dev \
    liblapack-dev \
    libhdf5-dev \
    libprotobuf-dev \
    protobuf-compiler \
    redis-server

echo "System dependency installation complete."
