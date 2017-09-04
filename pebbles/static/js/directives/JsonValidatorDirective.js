app.directive('jsonValidate', function () {
  return {
      require: 'ngModel',
      link: function(scope, element, attr, ngModelController) {
          function jsonValidator(value) {
              var exception = false;
              try {
                  parsed_value = JSON.parse(value);
              } catch (e) {
                  exception = true;
              }
              if (exception) {
                  ngModelController.$setValidity('jsonValid', false);
              }
              else {
                  ngModelController.$setValidity('jsonValid', true);
              }
              return parsed_value;
          }
          function jsonFormatter(value) {
              return JSON.stringify(value, null, 2);
          }
          ngModelController.$parsers.push(jsonValidator);
          ngModelController.$formatters.push(jsonFormatter);
      }
  };
});
