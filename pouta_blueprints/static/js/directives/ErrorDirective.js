app.directive('pbErrors', ['localStorageService', function(localStorageService) {
    return {
        restrict: 'E',
        link: function(scope, element, attrs) {
            var errors = localStorageService.get('errors');
            if (errors && (errors instanceof Array)) {
                errors.forEach(function(x) {
                    if (x.length != 2) {
                        return;
                    }
                    $.notify({message: "<b>" + x[0] + ":</b> " + x[1]}, {type: 'danger'});
                });
                localStorageService.set('errors', []);
            }
        }
    };
}]);
