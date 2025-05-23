# Copyright (c) 2011, Dorian Scholz, TU Darmstadt
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above
#     copyright notice, this list of conditions and the following
#     disclaimer in the documentation and/or other materials provided
#     with the distribution.
#   * Neither the name of the TU Darmstadt nor the names of its
#     contributors may be used to endorse or promote products derived
#     from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import array
import math
import random
import time
import re

from python_qt_binding.QtCore import Slot, QSignalMapper, QTimer, qWarning

from rclpy.exceptions import InvalidTopicNameException
from rclpy.qos import QoSProfile

from rosidl_runtime_py.utilities import get_message

from rqt_gui_py.plugin import Plugin
from rqt_py_common.topic_helpers import get_slot_type

from .publisher_widget import PublisherWidget

_list_types = [list, tuple, array.array]
try:
    import numpy
    _list_types.append(numpy.ndarray)
except ImportError:
    pass

_numeric_types = [int, float]
try:
    import numpy
    _numeric_types += [
        numpy.int8, numpy.int16, numpy.int32, numpy.int64,
        numpy.float16, numpy.float32, numpy.float64
    ]
except ImportError:
    pass

class Publisher(Plugin):

    def __init__(self, context):
        super(Publisher, self).__init__(context)
        self.setObjectName('Publisher')

        self._node = context.node

        # create widget
        self._widget = PublisherWidget(self._node)
        self._widget.add_publisher.connect(self.add_publisher)
        self._widget.change_publisher.connect(self.change_publisher)
        self._widget.publish_once.connect(self.publish_once)
        self._widget.remove_publisher.connect(self.remove_publisher)
        self._widget.clean_up_publishers.connect(self.clean_up_publishers)
        if context.serial_number() > 1:
            self._widget.setWindowTitle(
                self._widget.windowTitle() + (' (%d)' % context.serial_number()))

        # create context for the expression eval statement
        self._eval_locals = {'i': 0}
        self._eval_locals["now"] = self._get_time
        for module in (math, random, time, array):
            self._eval_locals.update(module.__dict__)
        del self._eval_locals['__name__']
        del self._eval_locals['__doc__']

        self._publishers = {}
        self._id_counter = 0

        self._timeout_mapper = QSignalMapper(self)
        self._timeout_mapper.mapped[int].connect(self.publish_once)

        # add our self to the main window
        context.add_widget(self._widget)

    @Slot(str, str, float, bool)
    def add_publisher(self, topic_name, type_name, rate, enabled):
        topic_name = str(topic_name)
        try:
            self._node._validate_topic_or_service_name(topic_name)
        except InvalidTopicNameException as e:
            qWarning(str(e))
            return

        publisher_info = {
            'topic_name': topic_name,
            'type_name': str(type_name),
            'rate': float(rate),
            'enabled': bool(enabled),
        }
        self._add_publisher(publisher_info)

    def _add_publisher(self, publisher_info):
        publisher_info['publisher_id'] = self._id_counter
        self._id_counter += 1
        publisher_info['counter'] = 0
        publisher_info['enabled'] = publisher_info.get('enabled', False)
        publisher_info['expressions'] = publisher_info.get('expressions', {})

        publisher_info['message_instance'] = self._create_message_instance(
            publisher_info['type_name'])
        if publisher_info['message_instance'] is None:
            return

        msg_module = get_message(publisher_info['type_name'])
        if not msg_module:
            raise RuntimeError(
                'The passed message type "{}" is invalid'.format(publisher_info['type_name']))

        # Topic name provided was relative, remap to node namespace (if it was set)
        if not publisher_info['topic_name'].startswith('/'):
            publisher_info['topic_name'] = \
                self._node.get_namespace() + publisher_info['topic_name']

        # create publisher and timer
        publisher_info['publisher'] = self._node.create_publisher(
            msg_module, publisher_info['topic_name'], qos_profile=QoSProfile(depth=10))
        publisher_info['timer'] = QTimer(self)

        # add publisher info to _publishers dict and create signal mapping
        self._publishers[publisher_info['publisher_id']] = publisher_info
        self._timeout_mapper.setMapping(publisher_info['timer'], publisher_info['publisher_id'])
        publisher_info['timer'].timeout.connect(self._timeout_mapper.map)
        if publisher_info['enabled'] and publisher_info['rate'] > 0:
            publisher_info['timer'].start(int(1000.0 / publisher_info['rate']))
        self._widget.publisher_tree_widget.model().add_publisher(publisher_info)

    @Slot(int, str, str, str, object)
    def change_publisher(self, publisher_id, topic_name, column_name, new_value, setter_callback):
        handler = getattr(self, '_change_publisher_%s' % column_name, None)
        if handler is not None:
            new_text = handler(self._publishers[publisher_id], topic_name, new_value)
            if new_text is not None:
                setter_callback(new_text)

    def _change_publisher_topic(self, publisher_info, topic_name, new_value):
        publisher_info['enabled'] = (new_value and new_value.lower() in ['1', 'true', 'yes'])
        if publisher_info['enabled'] and publisher_info['rate'] > 0:
            publisher_info['timer'].start(int(1000.0 / publisher_info['rate']))
        else:
            publisher_info['timer'].stop()
        return None

    def _change_publisher_type(self, publisher_info, topic_name, new_value):
        type_name = new_value
        # create new message field
        field_value = self._create_message_instance(type_name)

        # find parent field
        field_path = topic_name[len(publisher_info['topic_name']):].strip('/').split('/')
        parent_field = eval('.'.join(["publisher_info['message_instance']"] + field_path[:-1]))

        # find old message field
        field_name = field_path[-1]

        # restore type if user value was invalid
        if field_value is None:
            qWarning('Publisher._change_publisher_type(): could not find type: %s' % (type_name))
            return parent_field.get_fields_and_field_types()[field_name]

        else:
            # replace old message field
            parent_field.get_fields_and_field_types()[field_name] = type_name
            setattr(parent_field, field_name, field_value)

            self._widget.publisher_tree_widget.model().update_publisher(publisher_info)

    def _change_publisher_rate(self, publisher_info, topic_name, new_value):
        try:
            rate = float(new_value)
        except Exception:
            qWarning('Publisher._change_publisher_rate(): could not parse rate value: %s' %
                     (new_value))
        else:
            publisher_info['rate'] = rate
            publisher_info['timer'].stop()
            if publisher_info['enabled'] and publisher_info['rate'] > 0:
                publisher_info['timer'].start(int(1000.0 / publisher_info['rate']))
        # make sure the column value reflects the actual rate
        return '%.2f' % publisher_info['rate']

    def _change_publisher_expression(self, publisher_info, topic_name, new_value):
        user_expression = str(new_value)
        if len(user_expression) == 0:
            if topic_name in publisher_info['expressions']:
                del publisher_info['expressions'][topic_name]
                # qDebug(
                # 'Publisher._change_publisher_expression(): removed expression'
                # 'for: %s' % (topic_name))
        else:
            # Strip topic name from the full topic path
            slot_path = topic_name.replace(publisher_info['topic_name'], '', 1)
            slot_path, slot_array_index = self._extract_array_info(slot_path)
            slot_type = None

            # strip possible trailing error message from expression
            contains_error = re.match(r"(.*)\s*# error.*", user_expression)
            if contains_error:
                user_expression = contains_error.group(1)

            computed_expression = str(user_expression)
            # expression can contain topics with indexes, i.e. /chatter[0]
            # remove index to match message_instance, i.e. /chatter
            topic_name_includes_index = re.match(r"(.*)\[[0-9]*\]$", topic_name)
            if topic_name_includes_index:
                topic_name = topic_name_includes_index.group(1)

            # static sequences change one item at a time, impossible to validate
            # handle as entire sequence, enables validation
            if slot_array_index is not None:
                # remove first '/'
                slot_array = \
                    self._extract_slot_array(slot_path[1:].split('/'), publisher_info['message_instance'])
                slot_type = slot_array.__class__
                # quotes from gui are still present, remove them
                includes_quotes = re.match(r'^\s*[\'|\"](.*)[\'|\"]\s*$', computed_expression)
                if includes_quotes:
                    computed_expression = includes_quotes.group(1)
                # try to insert expression
                try:
                    slot_array[slot_array_index] = computed_expression
                except Exception as e:
                    return '%s # error: %s' % (user_expression, e)
                # expression is now full sequence
                computed_expression = slot_array

            # determine the property type, supplemental wrapper for get_slot_type()
            slot_type = \
                self._resolve_slot_type(computed_expression, slot_type, slot_path, publisher_info['message_instance'].__class__)
            success, _ = self._evaluate_expression(computed_expression, slot_type)
            if success:
                old_expression = publisher_info['expressions'].get(topic_name, None)
                publisher_info['expressions'][topic_name] = computed_expression
                try:
                    self._fill_message_slots(
                        publisher_info['message_instance'], publisher_info['topic_name'],
                        publisher_info['expressions'], publisher_info['counter'])
                except Exception as e:
                    if old_expression is not None:
                        publisher_info['expressions'][topic_name] = old_expression
                    else:
                        del publisher_info['expressions'][topic_name]
                    return '%s # error: %s' % (user_expression, e)
                return user_expression
            else:
                return '%s # error evaluating as "%s"' % (
                    user_expression, slot_type.__name__)

    def _extract_array_info(self, type_str):
        array_size = None
        if '[' in type_str and type_str[-1] == ']':
            type_str, array_size_str = type_str.split('[', 1)
            array_size_str = array_size_str[:-1]
            if len(array_size_str) > 0:
                array_size = int(array_size_str)
            else:
                array_size = 0

        return type_str, array_size

    def _extract_slot_array(self, slot_paths, slot_array):
        if len(slot_paths) == 0:
            return slot_array
        slot_array_name = '_' + slot_paths[0]
        slot_array = getattr(slot_array, slot_array_name)
        return self._extract_slot_array(slot_paths[1:], slot_array)

    def _resolve_slot_type(self, expression, slot_type, slot_path, message_class):
        if slot_type is None:
            # check for types that get_slot_type doesn't handle well
            # check for array.array type
            is_array_array = re.search(r"^array\(\'.\', (\[.*\])\)", expression)
            if is_array_array:
                return array.array

            # check for list type
            is_list = re.match(r"^\[.*\]\s*$", expression)
            if is_list:
                return list

            # check for string type
            is_string = re.match(r"^\'.*\'\s*$", expression)
            if is_string:
                return str

            # at this point, get_slot_type can determine the type
            slot_type, _ = \
                get_slot_type(message_class, slot_path)

        return slot_type

    def _create_message_instance(self, type_str):
        base_type_str, array_size = self._extract_array_info(type_str)

        try:
            base_message_type = get_message(base_type_str)
        except LookupError as e:
            qWarning("Creating message type {} failed. Please check your spelling and that the "
                     "message package has been built\n{}".format(base_type_str, e))
            return None

        if base_message_type is None:
            return None

        if array_size is not None:
            message = []
            for _ in range(array_size):
                message.append(base_message_type())
        else:
            message = base_message_type()
        return message

    def _get_time(self):
        return self._node.get_clock().now().to_msg()

    def _evaluate_expression(self, expression, slot_type):
        global _list_types
        global _numeric_types
        successful_eval = True
        try:
            # try to evaluate expression
            if isinstance(expression, str):
                value = eval(expression, {}, self._eval_locals)
            else:
                value = expression
        except Exception as e:
            qWarning('Python eval failed for expression "{}"'.format(expression) +
                     ' with an exception "{}"'.format(e))
            successful_eval = False
        if slot_type is str:
            if successful_eval:
                value = str(value)
            else:
                # for string slots just convert the expression to str, if it did not
                # evaluate successfully
                value = str(expression)
            successful_eval = True

        elif successful_eval:
            type_set = set((slot_type, type(value)))
            # check if value's type and slot_type belong to the same type group, i.e. array types,
            # numeric types and if they do, make sure values's type is converted to the exact
            # slot_type
            if type_set <= set(_list_types) or type_set <= set(_numeric_types):
                # convert to the right type
                if slot_type is not numpy.ndarray and slot_type is not array.array:
                    value = slot_type(value)

        if successful_eval and isinstance(value, slot_type):
            return True, value
        else:
            qWarning('Publisher._evaluate_expression(): failed to evaluate ' +
                     'expression: "%s" as Python type "%s"' % (
                      expression, slot_type))
        return False, None

    def _fill_message_slots(self, message, topic_name, expressions, counter):
        global _list_types
        if topic_name in expressions and len(expressions[topic_name]) > 0:
            # get type
            if hasattr(message, '_type'):
                message_type = message._type
            else:
                message_type = type(message)
            self._eval_locals['i'] = counter
            success, value = self._evaluate_expression(expressions[topic_name], message_type)
            if not success:
                value = message_type()
            return value

        # if no expression exists for this topic_name, continue with it's child slots
        elif hasattr(message, 'get_fields_and_field_types'):
            for slot_name in message.get_fields_and_field_types().keys():
                value = self._fill_message_slots(
                    getattr(message, slot_name),
                    topic_name + '/' + slot_name, expressions, counter)
                if value is not None:
                    setattr(message, slot_name, value)

        # This does not validate the entry because it tries to check each element and not whole list
        elif type(message) in _list_types and (len(message) > 0):
            for index, slot in enumerate(message):
                value = self._fill_message_slots(
                    slot, topic_name + '[%d]' % index, expressions, counter)
                # this deals with primitive-type arrays
                if not hasattr(message[0], '__slots__') and value is not None:
                    message[index] = value
        return None

    @Slot(int)
    def publish_once(self, publisher_id):
        publisher_info = self._publishers.get(publisher_id, None)
        if publisher_info is not None:
            publisher_info['counter'] += 1
            self._fill_message_slots(
                publisher_info['message_instance'],
                publisher_info['topic_name'],
                publisher_info['expressions'],
                publisher_info['counter'])
            publisher_info['publisher'].publish(publisher_info['message_instance'])

    @Slot(int)
    def remove_publisher(self, publisher_id):
        publisher_info = self._publishers.get(publisher_id, None)
        if publisher_info is not None:
            publisher_info['timer'].stop()
            self._node.destroy_publisher(publisher_info['publisher'])
            del publisher_info['publisher']
            del self._publishers[publisher_id]

    def save_settings(self, plugin_settings, instance_settings):
        publisher_copies = []
        for publisher in self._publishers.values():
            publisher_copy = {}
            publisher_copy.update(publisher)
            publisher_copy['enabled'] = False
            del publisher_copy['timer']
            del publisher_copy['message_instance']
            del publisher_copy['publisher']
            publisher_copies.append(publisher_copy)
        instance_settings.set_value('publishers', repr(publisher_copies))

    def restore_settings(self, plugin_settings, instance_settings):
        # If changing perspectives and rqt_publisher is already loaded, we need to clean up the
        # previously existing publishers
        self.clean_up_publishers()

        publishers = eval(instance_settings.value('publishers', '[]'))
        for publisher in publishers:
            self._add_publisher(publisher)

    def clean_up_publishers(self):
        self._widget.publisher_tree_widget.model().clear()
        for publisher_info in self._publishers.values():
            publisher_info['timer'].stop()
            self._node.destroy_publisher(publisher_info['publisher'])
        self._publishers = {}

    def shutdown_plugin(self):
        self._widget.shutdown_plugin()
        self.clean_up_publishers()
