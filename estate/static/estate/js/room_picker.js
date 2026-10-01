'use strict';
// The screen form's Room picker, narrowed to the building chosen above it.
//
// Django's autocomplete.js has already initialised the room select by the time
// this runs — RoomPickerWidget's media orders it first, and jQuery runs ready
// handlers in order. This re-initialises it so every request carries
// the building, and keeps it disabled until one is chosen. A disabled select is
// not submitted, so no building means no room.
{
    const $ = django.jQuery;

    function initRoomPicker(room) {
        const building = document.getElementById(room.dataset.buildingInput);
        if (!building) {
            return;
        }
        const $room = $(room);

        const build = () => {
            if ($room.hasClass('select2-hidden-accessible')) {
                $room.select2('destroy');
            }
            const chosen = building.value !== '';
            room.disabled = !chosen;
            // Not a select2 option: select2 lets data-* override options, and
            // Django's widget renders data-placeholder="". Not the attribute
            // either: select2 reads it through jQuery's .data(), which cached
            // the first value when autocomplete.js initialised the select.
            $room.data('placeholder', chosen ? '' : 'Choose a building first');
            $room.select2({
                ajax: {
                    data: (params) => ({
                        term: params.term,
                        page: params.page,
                        app_label: room.dataset.appLabel,
                        model_name: room.dataset.modelName,
                        field_name: room.dataset.fieldName,
                        building: building.value,
                    }),
                },
            });
        };

        // select2 reports a choice with jQuery's trigger(), which native
        // addEventListener handlers never see.
        $(building).on('change', () => {
            $room.val(null).trigger('change');
            build();
        });
        // select2 4.0.13 does not focus its search box on open under jQuery
        // 3.6, so typing straight after clicking would go nowhere. Bound
        // outside build(): select2's destroy only removes its own namespaced
        // handlers, so these survive every re-initialisation.
        const focusSearch = () => {
            const field = document.querySelector(
                '.select2-container--open .select2-search__field');
            if (field) {
                field.focus();
            }
        };
        $(building).on('select2:open', focusSearch);
        $room.on('select2:open', focusSearch);
        build();
    }

    $(function() {
        document.querySelectorAll('select[data-building-input]').forEach(initRoomPicker);
    });
}
