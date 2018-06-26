app.directive('configurableValue', ['ConfigurationService', function(ConfigurationService) {
    return {
        restrict: 'EA',
        link: function(scope, element, attrs) {
            ConfigurationService.getValue().then(function (data) {
                element.text(data[attrs.key]);
            });
        }
    };
}]);

app.directive('configurableHref', ['ConfigurationService', function(ConfigurationService) {
    return {
        restrict: 'EA',
        link: function(scope, element, attrs) {
            ConfigurationService.getValue().then(function (data) {
                element.html('<a href="'+data[attrs.key]+'" target="blank">'+attrs.name+'</a>');
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
app.directive('brandImage', ['ConfigurationService', function(ConfigurationService) {
    return {
        restrict: 'A',
        link: function(scope, element, attrs) {
            ConfigurationService.getValue().then(function (data) {
                if (data[attrs.key]) {
                    element.html('<img style="width:100%; height:auto;" src="' + data[attrs.key] + '">');
                } else if (data[attrs.altKey]) {
                    element.text(data[attrs.altKey]);
                } else {
                    element.text(attrs.alt);
                }
            }); 
        }
    };
}]);
