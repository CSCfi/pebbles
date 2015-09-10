app.directive('configurableValue', ['ConfigurationService', function(ConfigurationService) {
    return {
        restrict: 'E',
        link: function(scope, element, attrs) {
            ConfigurationService.getValue().then(function (data) {
                element.text(data[attrs.key]);
            }); 
        }
    };
}]);

app.directive('configurableShow', ['ConfigurationService', function(ConfigurationService) {
    return {
        restrict: 'A',
        link: function(scope, element, attrs) {
            ConfigurationService.getValue().then(function (data) {
                if (data[attrs.key]) {
                    element.show();
                } else {
                    element.hide();
                }
            }); 
        }
    };
}]);
