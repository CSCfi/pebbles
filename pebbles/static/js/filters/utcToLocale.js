app.filter('utcToLocale', function ($filter) {
    return function (input, format) {
        if (input) {
            return $filter('date')(new Date(input), format);
        }
    };
});
