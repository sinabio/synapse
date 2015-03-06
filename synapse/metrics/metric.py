# -*- coding: utf-8 -*-
# Copyright 2015 OpenMarket Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


from itertools import chain


# TODO(paul): I can't believe Python doesn't have one of these
def map_concat(func, items):
    # flatten a list-of-lists
    return list(chain.from_iterable(map(func, items)))


class BaseMetric(object):

    def __init__(self, name, labels=[]):
        self.name = name
        self.labels = labels # OK not to clone as we never write it

    def dimension(self):
        return len(self.labels)

    def is_scalar(self):
        return not len(self.labels)

    def _render_key(self, values):
        if self.is_scalar():
            return ""
        # TODO: some kind of value escape
        return "{%s}" % (
            ",".join(["%s=%s" % kv for kv in zip(self.labels, values)])
        )

    def render(self):
        return map_concat(self.render_item, sorted(self.counts.keys()))


class CounterMetric(BaseMetric):
    """The simplest kind of metric; one that stores a monotonically-increasing
    integer that counts events."""

    def __init__(self, *args, **kwargs):
        super(CounterMetric, self).__init__(*args, **kwargs)

        self.counts = {}

        # Scalar metrics are never empty
        if self.is_scalar():
            self.counts[()] = 0

    def inc(self, *values):
        if len(values) != self.dimension():
            raise ValueError("Expected as many values to inc() as labels (%d)" %
                (self.dimension())
            )

        # TODO: should assert that the tag values are all strings

        if values not in self.counts:
            self.counts[values] = 1
        else:
            self.counts[values] += 1

    def render_item(self, k):
        return ["%s%s %d" % (self.name, self._render_key(k), self.counts[k])]


class CallbackMetric(BaseMetric):
    """A metric that returns the numeric value returned by a callback whenever
    it is rendered. Typically this is used to implement gauges that yield the
    size or other state of some in-memory object by actively querying it."""

    def __init__(self, name, callback, labels=[]):
        super(CallbackMetric, self).__init__(name, labels=labels)

        self.callback = callback

    def render(self):
        value = self.callback()

        if self.is_scalar():
            return ["%s %d" % (self.name, value)]

        return ["%s%s %d" % (self.name, self._render_key(k), value[k])
                for k in sorted(value.keys())]


class TimerMetric(CounterMetric):
    """A combination of an event counter and a time accumulator, which counts
    both the number of events and how long each one takes.

    TODO(paul): Try to export some heatmap-style stats?
    """

    def __init__(self, *args, **kwargs):
        super(TimerMetric, self).__init__(*args, **kwargs)

        self.times = {}

        # Scalar metrics are never empty
        if self.is_scalar():
            self.times[()] = 0

    def inc_time(self, msec, *values):
        self.inc(*values)

        if values not in self.times:
            self.times[values] = msec
        else:
            self.times[values] += msec

    def render_item(self, k):
        keystr = self._render_key(k)

        return ["%s:count%s %d" % (self.name, keystr, self.counts[k]),
                "%s:msec%s %d" % (self.name, keystr, self.times[k])]


class CacheMetric(object):
    """A combination of two CounterMetrics, one to count cache hits and one to
    count misses, and a callback metric to yield the current size.

    This metric generates standard metric name pairs, so that monitoring rules
    can easily be applied to measure hit ratio."""

    def __init__(self, name, size_callback, labels=[]):
        self.name = name

        self.hits   = CounterMetric(name + ":hits",   labels=labels)
        self.misses = CounterMetric(name + ":misses", labels=labels)

        self.size = CallbackMetric(name + ":size",
            callback=size_callback,
            labels=labels,
        )

    def inc_hits(self, *values):
        self.hits.inc(*values)

    def inc_misses(self, *values):
        self.misses.inc(*values)

    def render(self):
        return self.hits.render() + self.misses.render() + self.size.render()
