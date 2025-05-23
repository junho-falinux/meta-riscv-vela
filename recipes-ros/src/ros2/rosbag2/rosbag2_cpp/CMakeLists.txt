cmake_minimum_required(VERSION 3.5)
project(rosbag2_cpp)

add_definitions(-D_SRC_REINDEX_DIR_PATH="${CMAKE_CURRENT_SOURCE_DIR}/test/rosbag2_cpp/reindex_test_bags")

# Default to C99
if(NOT CMAKE_C_STANDARD)
  set(CMAKE_C_STANDARD 99)
endif()

# Default to C++17
if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
  set(CMAKE_CXX_STANDARD_REQUIRED ON)
endif()

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()
if(CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wthread-safety)
endif()

# Windows supplies macros for min and max by default. We should only use min and max from stl
if(WIN32)
  add_definitions(-DNOMINMAX)
endif()

option(DISABLE_SANITIZERS "disables the use of gcc sanitizers" ON)
if(NOT DISABLE_SANITIZERS AND CMAKE_COMPILER_IS_GNUCXX)
  include(CheckCXXSourceRuns)
  set(OLD_CMAKE_REQUIRED_FLAGS ${CMAKE_REQUIRED_FLAGS})
  set(CMAKE_REQUIRED_FLAGS "${OLD_CMAKE_REQUIRED_FLAGS} -fsanitize=address,leak,undefined")
  check_cxx_source_runs("int main() {}" HAVE_SANITIZERS)
  set(CMAKE_REQUIRED_FLAGS ${OLD_CMAKE_REQUIRED_FLAGS})
  if(NOT HAVE_SANITIZERS)
    set(DISABLE_SANITIZERS ON)
    message(WARNING "Sanitizers aren't supported by the compiler or environment - disabling")
  endif()
endif()

find_package(ament_cmake REQUIRED)
find_package(ament_index_cpp REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(rcpputils REQUIRED)
find_package(rcutils REQUIRED)
find_package(rmw REQUIRED)
find_package(rmw_implementation REQUIRED)
find_package(rosbag2_storage REQUIRED)
find_package(rosidl_runtime_c REQUIRED)
find_package(rosidl_runtime_cpp REQUIRED)
find_package(rosidl_typesupport_cpp REQUIRED)
find_package(rosidl_typesupport_introspection_cpp REQUIRED)

add_library(${PROJECT_NAME} SHARED
  src/rosbag2_cpp/cache/cache_consumer.cpp
  src/rosbag2_cpp/cache/message_cache_buffer.cpp
  src/rosbag2_cpp/cache/message_cache_circular_buffer.cpp
  src/rosbag2_cpp/cache/message_cache.cpp
  src/rosbag2_cpp/cache/circular_message_cache.cpp
  src/rosbag2_cpp/clocks/time_controller_clock.cpp
  src/rosbag2_cpp/converter.cpp
  src/rosbag2_cpp/info.cpp
  src/rosbag2_cpp/message_definitions/local_message_definition_source.cpp
  src/rosbag2_cpp/reader.cpp
  src/rosbag2_cpp/readers/sequential_reader.cpp
  src/rosbag2_cpp/rmw_implemented_serialization_format_converter.cpp
  src/rosbag2_cpp/serialization_format_converter_factory.cpp
  src/rosbag2_cpp/types/introspection_message.cpp
  src/rosbag2_cpp/typesupport_helpers.cpp
  src/rosbag2_cpp/types/introspection_message.cpp
  src/rosbag2_cpp/writer.cpp
  src/rosbag2_cpp/writers/sequential_writer.cpp
  src/rosbag2_cpp/reindexer.cpp
  src/rosbag2_cpp/service_utils.cpp)

target_link_libraries(${PROJECT_NAME} PUBLIC
  pluginlib::pluginlib
  rclcpp::rclcpp
  rcpputils::rcpputils
  rcutils::rcutils
  rmw::rmw
  rmw_implementation::rmw_implementation
  rosbag2_storage::rosbag2_storage
  rosidl_runtime_c::rosidl_runtime_c
  rosidl_runtime_cpp::rosidl_runtime_cpp
  rosidl_typesupport_introspection_cpp::rosidl_typesupport_introspection_cpp
)
target_link_libraries(${PROJECT_NAME} PRIVATE
  ament_index_cpp::ament_index_cpp
  rosidl_typesupport_cpp::rosidl_typesupport_cpp
)

target_include_directories(${PROJECT_NAME}
  PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include/${PROJECT_NAME}>
)

# Causes the visibility macros to use dllexport rather than dllimport,
# which is appropriate when building the dll but not consuming it.
target_compile_definitions(${PROJECT_NAME} PRIVATE "ROSBAG2_CPP_BUILDING_DLL")

install(
  DIRECTORY include/
  DESTINATION include/${PROJECT_NAME})

install(
  TARGETS ${PROJECT_NAME}
  EXPORT export_${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin)

# Export old-style CMake variables
ament_export_include_directories("include/${PROJECT_NAME}")
ament_export_libraries(${PROJECT_NAME})

# Export modern CMake targets
ament_export_targets(export_${PROJECT_NAME})

ament_export_dependencies(
  pluginlib
  rclcpp
  rcpputils
  rcutils
  rmw
  rmw_implementation
  rosbag2_storage
  rosidl_runtime_c
  rosidl_runtime_cpp
  rosidl_typesupport_introspection_cpp
)

if(BUILD_TESTING)
  find_package(ament_cmake_gmock REQUIRED)
  find_package(ament_lint_auto REQUIRED)
  find_package(test_msgs REQUIRED)
  find_package(std_msgs REQUIRED)
  find_package(rosbag2_test_msgdefs REQUIRED)
  find_package(rmw_implementation_cmake REQUIRED)
  ament_lint_auto_find_test_dependencies()

  add_library(
    converter_test_plugins
    SHARED
    test/rosbag2_cpp/serializer_test_plugin.cpp
    test/rosbag2_cpp/converter_test_plugin.cpp)
  target_link_libraries(converter_test_plugins
    ${PROJECT_NAME}
    rosbag2_storage::rosbag2_storage
  )
  install(
    TARGETS converter_test_plugins
    ARCHIVE DESTINATION lib
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION bin)
  pluginlib_export_plugin_description_file(rosbag2_cpp test/rosbag2_cpp/converter_test_plugin.xml)

  ament_add_gmock(test_converter_factory
    test/rosbag2_cpp/test_converter_factory.cpp)
  if(TARGET test_converter_factory)
    target_link_libraries(test_converter_factory ${PROJECT_NAME})
  endif()

  ament_add_gmock(test_typesupport_helpers
    test/rosbag2_cpp/test_typesupport_helpers.cpp
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
  if(TARGET test_typesupport_helpers)
    target_link_libraries(test_typesupport_helpers
      ${PROJECT_NAME}
      ament_index_cpp::ament_index_cpp
      rosidl_typesupport_cpp::rosidl_typesupport_cpp
    )
  endif()

  ament_add_gmock(test_info
    test/rosbag2_cpp/test_info.cpp
    WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR})
  if(TARGET test_info)
    target_link_libraries(test_info ${PROJECT_NAME} rosbag2_test_common::rosbag2_test_common ${test_msgs_TARGETS})
  endif()

  ament_add_gmock(test_sequential_reader
    test/rosbag2_cpp/test_sequential_reader.cpp test/rosbag2_cpp/fake_data.cpp)
  if(TARGET test_sequential_reader)
    target_link_libraries(test_sequential_reader
      ${PROJECT_NAME}
      rosbag2_storage::rosbag2_storage
      rosbag2_test_common::rosbag2_test_common
      ${test_msgs_TARGETS}
      ${std_msgs_TARGETS}
    )
  endif()

  ament_add_gmock(test_storage_without_metadata_file
    test/rosbag2_cpp/test_storage_without_metadata_file.cpp)
  if(TARGET test_storage_without_metadata_file)
    target_link_libraries(test_storage_without_metadata_file ${PROJECT_NAME} rosbag2_storage::rosbag2_storage)
  endif()

  ament_add_gmock(test_local_message_definition_source
    test/rosbag2_cpp/test_local_message_definition_source.cpp)
  if(TARGET test_local_message_definition_source)
    target_link_libraries(test_local_message_definition_source ${PROJECT_NAME})
  endif()

  ament_add_gmock(test_message_cache
    test/rosbag2_cpp/test_message_cache.cpp)
  if(TARGET test_message_cache)
    target_link_libraries(test_message_cache ${PROJECT_NAME})
  endif()

  ament_add_gmock(test_circular_message_cache
    test/rosbag2_cpp/test_circular_message_cache.cpp)
  if(TARGET test_circular_message_cache)
    target_link_libraries(test_circular_message_cache ${PROJECT_NAME})
  endif()


  # If compiling with gcc, run this test with sanitizers enabled
  ament_add_gmock(test_ros2_message
    test/rosbag2_cpp/types/test_ros2_message.cpp
    src/rosbag2_cpp/typesupport_helpers.cpp
    src/rosbag2_cpp/types/introspection_message.cpp)
  if(TARGET test_ros2_message)
    target_compile_definitions(test_ros2_message PRIVATE "ROSBAG2_CPP_BUILDING_DLL")
    if(NOT DISABLE_SANITIZERS)
      target_compile_options(test_ros2_message PUBLIC $<$<CXX_COMPILER_ID:GNU>:-fsanitize=leak>)
      target_link_libraries(test_ros2_message $<$<CXX_COMPILER_ID:GNU>:-fsanitize=leak>)
    endif()
    target_include_directories(test_ros2_message
      PUBLIC
      $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>)
    target_link_libraries(test_ros2_message
      ament_index_cpp::ament_index_cpp
      rcpputils::rcpputils
      rosbag2_storage::rosbag2_storage
      rosidl_runtime_cpp::rosidl_runtime_cpp
      rosidl_typesupport_introspection_cpp::rosidl_typesupport_introspection_cpp
      rosidl_typesupport_cpp::rosidl_typesupport_cpp
      ${test_msgs_TARGETS}
    )
  endif()

  ament_add_gmock(test_sequential_writer
    test/rosbag2_cpp/test_sequential_writer.cpp test/rosbag2_cpp/fake_data.cpp)
  if(TARGET test_sequential_writer)
    target_link_libraries(test_sequential_writer
      ${PROJECT_NAME}
      rosbag2_storage::rosbag2_storage
      rosbag2_test_common::rosbag2_test_common
      ${test_msgs_TARGETS}
    )
  endif()

  ament_add_gmock_executable(test_serialization_converter test/rosbag2_cpp/test_serialization_converter.cpp)
  if(TARGET test_serialization_converter)
    if(NOT DISABLE_SANITIZERS)
      target_compile_options(test_serialization_converter PUBLIC $<$<CXX_COMPILER_ID:GNU>:-fsanitize=address,leak,undefined>)
      target_link_libraries(test_serialization_converter $<$<CXX_COMPILER_ID:GNU>:-fsanitize=address,leak,undefined>)
    endif()
    target_link_libraries(test_serialization_converter
      ${PROJECT_NAME}
      rosbag2_storage::rosbag2_storage
      ${std_msgs_TARGETS}
    )
  endif()

  function(test_serialization_converter_for_rmw_implementation)
    set(rmw_implementation_env_var RMW_IMPLEMENTATION=${rmw_implementation})
    ament_add_gmock_test(test_serialization_converter
      TEST_NAME test_serialization_converter${target_suffix}
      ENV ${rmw_implementation_env_var}
    )
  endfunction()
  # Run test_serialization_converter for each rmw implementation because default serialization
  # converter uses rmw specific functions for serialization and deserialization.
  call_for_each_rmw_implementation(test_serialization_converter_for_rmw_implementation)

  ament_add_gmock(test_multifile_reader
    test/rosbag2_cpp/test_multifile_reader.cpp)
  if(TARGET test_multifile_reader)
    target_link_libraries(test_multifile_reader
      ${PROJECT_NAME}
      rosbag2_storage::rosbag2_storage
    )
  endif()

  ament_add_gmock(test_time_controller_clock
    test/rosbag2_cpp/test_time_controller_clock.cpp)
  if(TARGET test_time_controller_clock)
    target_link_libraries(test_time_controller_clock ${PROJECT_NAME})
  endif()

  ament_add_gmock(test_service_utils
    test/rosbag2_cpp/test_service_utils.cpp)
  if(TARGET test_service_utils)
    target_link_libraries(test_service_utils
      ${PROJECT_NAME}
      rosbag2_test_common::rosbag2_test_common
      ${test_msgs_TARGETS}
    )
  endif()
endif()

ament_package()
