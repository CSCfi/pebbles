app.directive('editablefield', function() {
    return {
        restrict: 'E',
        template: '<div><span ng-hide="editActive" ng-class="viewClass">{{ text }} </span> <form class="form-inline" ng-show="editActive"><input type="text" class="form-control"> <button class="btn btn-primary" type="submit"> <span class="glyphicon glyphicon-ok" aria-hidden="true"></span></button> <button type="button" class="btn btn-default"> <span class="glyphicon glyphicon-remove" aria-hidden="true"></span></button> </form></div>',
        scope: {
            text: '=model',
            onReady: '&',
            viewClass: '@',
            editClass: '@'
        },
        replace: true,
        link: function(scope, element, attrs) {
            scope.editActive = false;
            var span = angular.element(element.children()[0]);
            var form = angular.element(element.children()[1]);
            var input = angular.element(element.children()[1][0]);
            var cancel = angular.element(element.children()[1][2]);

            span.bind('click', function(event) {
                input[0].value = scope.text;
                bindElements();
                scope.editActive = true;
                scope.$apply();
                input[0].focus();
            });

            cancel.bind('click', function(event) {
                disableEdit();
            });

            function bindElements() {
                form.bind('submit', function() {
                    if (input[0].value) {
                        save();
                    }
                    disableEdit();
                });
            }

            function disableEdit() {
                unbindElements();
                scope.editActive = false;
                scope.$apply();
            }

            function unbindElements() {
                form.unbind();
            }

            function save() {
                scope.text = input[0].value;
                scope.$apply();
                scope.onReady();
            }
        }
    };
});
