/*
 * Two fixes on top of django-recurrence's vendored widget.
 *
 * 1. Re-init on new inline rows. The upstream init script observes #container
 *    for added rows, and Unfold doesn't render that element.
 *
 * 2. The monthly day grid's last four cells. Upstream draws 35 cells and prints
 *    `number - 36` in the overflow, giving -4 -3 -2 -1 with no label anywhere --
 *    they are RFC 5545 negative BYMONTHDAY, i.e. "4th from last" through "last
 *    day of the month", and -1 is the only way to say "last day" for a month
 *    that may be 28, 29, 30 or 31 days long.
 *
 *    Worse, upstream highlights the saved selection with
 *    `this.rule.bymonthday.indexOf(number)` using the loop counter 1..35 rather
 *    than the value shown, so a stored -1 never renders as selected. Reopen such
 *    a rule and the grid looks empty; click anywhere and set_bymonthday()
 *    rebuilds the list from highlighted cells only, silently dropping it. That
 *    is data loss on edit, so we restore the highlight here.
 *
 *    Done with a MutationObserver rather than by patching the widget prototype:
 *    this file loads before recurrence-widget.js, and jQuery's ready callbacks
 *    (which build the widgets) run before any handler we could register. The
 *    observer catches grids however they arrive -- initial render, a change of
 *    frequency, or a newly added inline row.
 *
 *    Cell text is never modified. set_bymonthday() reads values back with
 *    parseInt(cell.innerHTML), so a label in the text node would parse to NaN
 *    and drop the day. The label goes in `title` and a data attribute instead.
 */
(function () {
    'use strict';

    var FROM_END = {
        '-1': ['Last day of the month', 'last'],
        '-2': ['2nd from last day of the month', '2nd from last'],
        '-3': ['3rd from last day of the month', '3rd from last'],
        '-4': ['4th from last day of the month', '4th from last']
    };

    function hasClass(el, name) {
        return (' ' + el.className + ' ').indexOf(' ' + name + ' ') > -1;
    }

    function addClass(el, name) {
        if (!hasClass(el, name)) {
            el.className = el.className ? el.className + ' ' + name : name;
        }
    }

    /* The widget root is inserted immediately before its own textarea, which
     * still holds the serialized value. */
    function storedNegativeMonthdays(grid) {
        var root = grid.closest && grid.closest('div.recurrence-widget');
        var textarea = root && root.nextElementSibling;
        if (!textarea || textarea.tagName !== 'TEXTAREA') {
            return [];
        }
        var found = [];
        (textarea.value || '').split(/\r?\n/).forEach(function (line) {
            if (line.indexOf('RRULE') !== 0) {
                return;
            }
            var match = /BYMONTHDAY=([-\d,]+)/.exec(line);
            if (!match) {
                return;
            }
            match[1].split(',').forEach(function (value) {
                var day = parseInt(value, 10);
                if (day < 0) {
                    found.push(day);
                }
            });
        });
        return found;
    }

    function decorate(grid) {
        if (grid.getAttribute('data-monthday-decorated')) {
            return;
        }
        var negatives = null;
        Array.prototype.forEach.call(grid.querySelectorAll('td'), function (cell) {
            var text = (cell.textContent || '').trim();
            var label = FROM_END[text];
            if (!label) {
                return;
            }
            // Only a monthly day grid carries these; mark it so we run once.
            grid.setAttribute('data-monthday-decorated', '1');
            cell.title = label[0];
            cell.setAttribute('data-monthday-caption', label[1]);
            addClass(cell, 'monthday-from-end');

            if (negatives === null) {
                negatives = storedNegativeMonthdays(grid);
            }
            if (negatives.indexOf(parseInt(text, 10)) > -1) {
                addClass(cell, 'active');
            }
        });
    }

    function scan(node) {
        if (!node || node.nodeType !== 1) {
            return;
        }
        if (node.matches && node.matches('table.grid')) {
            decorate(node);
        }
        if (node.querySelectorAll) {
            Array.prototype.forEach.call(
                node.querySelectorAll('table.grid'), decorate);
        }
    }

    new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            Array.prototype.forEach.call(mutation.addedNodes, scan);
        });
    }).observe(document.documentElement, {childList: true, subtree: true});

    document.addEventListener('DOMContentLoaded', function () {
        scan(document.body);
    });

    document.addEventListener('formset:added', function (event) {
        var $field = django.jQuery(event.target)
            .find('textarea.recurrence-widget:not([id*="__prefix__"])');
        if ($field.length) {
            initRecurrenceWidget($field);
        }
    });
}());
