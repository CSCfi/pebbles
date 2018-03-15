app.filter('utcToLocale', function ($filter) {
    /* This will add 'Z' to denote that api returned time in UTC.
     * so local time will be displayed in UI. */
    return function (input, format) {
        if (input) {
            if (input.indexOf('Z') === -1 && input.indexOf('+') === -1) {
                input += 'Z';
            }
            return $filter('date')(input, format);
            }
        };
});
