# Copyright (c) 2011, Dorian Scholz, TU Darmstadt
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#
#    * Neither the name of the TU Darmstadt nor the names of its
#      contributors may be used to endorse or promote products derived from
#      this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE
# ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE
# LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS
# INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN
# CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE)
# ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

import argparse

from python_qt_binding import QT_BINDING
from python_qt_binding.QtCore import qDebug
from rqt_gui_py.plugin import Plugin

from rqt_py_common.ini_helper import pack, unpack

from .plot_widget import PlotWidget

from .data_plot import DataPlot


class Plot(Plugin):

    def __init__(self, context):
        super(Plot, self).__init__(context)
        self.setObjectName('Plot')

        self._context = context
        self._node = context.node
        self._args = self._parse_args(context.argv())
        self._widget = PlotWidget(
            self._node, initial_topics=self._args.topics, start_paused=self._args.start_paused)
        self._data_plot = DataPlot(self._widget)

        # disable autoscaling of X, and set a sane default range
        self._data_plot.set_autoscale(x=False)
        self._data_plot.set_autoscale(y=DataPlot.SCALE_EXTEND | DataPlot.SCALE_VISIBLE)
        self._data_plot.set_xlim([0, 10.0])

        self._widget.switch_data_plot_widget(self._data_plot)
        if context.serial_number() > 1:
            self._widget.setWindowTitle(
                self._widget.windowTitle() + (' (%d)' % context.serial_number()))
        context.add_widget(self._widget)

    def _resolve_topic_name(self, script_name, name):
        """
        Name resolver for scripts.

        Derived from
            https://github.com/ros/ros_comm/blob/melodic-devel/tools/rosgraph/src/rosgraph/names.py

        :param name: name to resolve, ``str``
        :param script_name: name of script. script_name must not
          contain a namespace., ``str``
        :returns: resolved name, ``str``
        """
        sep = '/'
        priv_name = '~'

        # empty string resolves to namespace
        if not name:
            return self._node.get_namespace()
        # Check for global name: /foo/name resolves to /foo/name
        if name[0] == sep:
            return name
        # Check for private name: ~name resolves to /caller_id/name
        elif name[0] == priv_name:
            if script_name[-1] == sep:
                return script_name + name[1:]
            return script_name + sep + name[1:]
        return self._node.get_namespace() + name

    def _parse_args(self, argv):
        parser = argparse.ArgumentParser(prog='rqt_plot', add_help=False)
        Plot.add_arguments(parser)
        args = parser.parse_args(argv)

        # convert topic arguments into topic names
        topic_list = []
        for t in args.topics:
            # c_topics is the list of topics to plot
            c_topics = []
            # compute combined topic list, t == '/foo/bar1,/baz/bar2'
            for sub_t in [x for x in t.split(',') if x]:
                # check for shorthand '/foo/field1:field2:field3'
                if ':' in sub_t:
                    base = sub_t[:sub_t.find(':')]
                    # the first prefix includes a field name, so save then strip it off
                    c_topics.append(base)
                    if '/' not in base:
                        parser.error("%s must contain a topic and field name" % sub_t)
                    base = base[:base.rfind('/')]

                    # compute the rest of the field names
                    fields = sub_t.split(':')[1:]
                    c_topics.extend(["%s/%s" % (base, f) for f in fields if f])
                else:
                    c_topics.append(sub_t)

            c_topics = [self._resolve_topic_name('rqt_plot', n) for n in c_topics]
            topic_list.extend(c_topics)

        args.topics = topic_list

        return args

    @staticmethod
    def add_arguments(parser):
        group = parser.add_argument_group('Options for rqt_plot plugin')
        group.add_argument('-P', '--pause', action='store_true', dest='start_paused',
                           help='Start in paused state')
        group.add_argument('-e', '--empty', action='store_true', dest='start_empty',
                           help='Start without restoring previous topics')
        group.add_argument('topics', nargs='*', default=[], help='Topics to plot')

    def _update_title(self):
        self._widget.setWindowTitle(self._data_plot.getTitle())
        if self._context.serial_number() > 1:
            self._widget.setWindowTitle(
                self._widget.windowTitle() + (' (%d)' % self._context.serial_number()))

    def save_settings(self, plugin_settings, instance_settings):
        self._data_plot.save_settings(plugin_settings, instance_settings)
        instance_settings.set_value('autoscroll', self._widget.autoscroll_checkbox.isChecked())
        instance_settings.set_value('topics', pack(self._widget._rosdata.keys()))

    def restore_settings(self, plugin_settings, instance_settings):
        autoscroll = instance_settings.value('autoscroll', True) in [True, 'true']
        self._widget.autoscroll_checkbox.setChecked(autoscroll)
        self._data_plot.autoscroll(autoscroll)

        self._update_title()

        if len(self._widget._rosdata.keys()) == 0 and not self._args.start_empty:
            topics = unpack(instance_settings.value('topics', []))
            if topics:
                for topic in topics:
                    self._widget.add_topic(topic)

        self._data_plot.restore_settings(plugin_settings, instance_settings)

    def trigger_configuration(self):
        self._data_plot.doSettingsDialog()
        self._update_title()

    def shutdown_plugin(self):
        self._widget.clean_up_subscribers()
