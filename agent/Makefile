CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -pthread
TARGET = agent
TEST_TARGET = test_client
SOURCES = main.cpp node_agent.cpp http_server.cpp
TEST_SOURCES = test_client.cpp
OBJECTS = $(SOURCES:.cpp=.o)
TEST_OBJECTS = $(TEST_SOURCES:.cpp=.o)

.PHONY: all clean test_client

all: $(TARGET) $(TEST_TARGET)

$(TARGET): $(OBJECTS)
	$(CXX) $(OBJECTS) -o $(TARGET) $(CXXFLAGS)

$(TEST_TARGET): $(TEST_OBJECTS)
	$(CXX) $(TEST_OBJECTS) -o $(TEST_TARGET) $(CXXFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJECTS) $(TEST_OBJECTS) $(TARGET) $(TEST_TARGET)

install: $(TARGET)
	cp $(TARGET) /usr/local/bin/

uninstall:
	rm -f /usr/local/bin/$(TARGET)

test: $(TARGET) $(TEST_TARGET)
	@echo "Running basic tests..."
	@echo "Note: This requires a Linux environment with /proc filesystem"
	@echo "Tests would include:"
	@echo "  - Starting the agent on a test port"
	@echo "  - Sending HTTP requests to the agent"
	@echo "  - Verifying process management"
	@echo "  - Checking metrics collection"

help:
	@echo "Available targets:"
	@echo "  all         - Build the Node Agent and test client (default)"
	@echo "  agent       - Build only the Node Agent"
	@echo "  test_client - Build only the test client"
	@echo "  clean       - Remove build artifacts"
	@echo "  install     - Install to /usr/local/bin/"
	@echo "  uninstall   - Remove from /usr/local/bin/"
	@echo "  test        - Show test information"
	@echo "  help        - Show this help message" 